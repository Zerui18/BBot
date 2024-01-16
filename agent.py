import requests
import base64
from pprint import pformat
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dataclasses import dataclass
from logging import Logger
from ocr_solver import OCRSolver

@dataclass
class Slot:
    slotId: int
    slotIdEnc: str
    slotRefName: str
    slotRefDate: str
    startTime: str
    endTime: str
    totalFee: float
    userGroupNo: str
    bookingProgress: str
    bookingProgressEnc: str

    @classmethod
    def from_dict(cls, data):
        return cls(
            slotId=data['slotId'],
            slotIdEnc=data['slotIdEnc'],
            slotRefName=data['slotRefName'],
            slotRefDate=data['slotRefDate'],
            startTime=data['startTime'],
            endTime=data['endTime'],
            totalFee=data['totalFee'],
            userGroupNo=data['userFixGrpNo'],
            bookingProgress=data['bookingProgress'],
            bookingProgressEnc=data['bookingProgressEnc']
        )
    
    def is_available(self):
        return self.bookingProgress == 'Available'

    def __str__(self):
        return f'{self.slotRefName} on {self.slotRefDate} from {self.startTime} to {self.endTime}, costing ${self.totalFee}.'

@dataclass
class BookedSlot:
    bookingId: int
    theoryType: str
    dataType: str
    slotRefName: str
    slotRefDesc: str
    slotRefDate: str
    startTime: str
    endTime: str
    totalFee: float
    userGroupNo: str
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            bookingId=data['bookingId'],
            theoryType=data['theoryType'],
            dataType=data['dataType'],
            slotRefName=data['slotRefName'],
            slotRefDesc=data['slotRefDesc'],
            slotRefDate=data['slotRefDate'],
            startTime=data['startTime'],
            endTime=data['endTime'],
            totalFee=data['totalFee'],
            userGroupNo=data['userFixGrpNo']
        )
    
    def __str__(self):
        return f'[Booked] {self.slotRefName} on {self.slotRefDate} from {self.startTime} to {self.endTime}, costing ${self.totalFee}.'

class Agent:

    def __init__(self, logger: Logger):
        self.__ocr_solver = OCRSolver()
        self.__logger = logger

    headers = {
        'authority': 'booking.bbdc.sg',
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'jsessionid': '',
        'origin': 'https://booking.bbdc.sg',
        'referer': 'https://booking.bbdc.sg/?',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36     (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36'
    }
    authorization_token = ''
    course_authorization_token = ''
    saved_username = ''
    saved_password = ''

    def __debug(self, msg: str):
        ''' Log a debug message. '''
        self.__logger.debug(msg)
    
    def __info(self, msg: str):
        ''' Log an info message. '''
        self.__logger.info(msg)

    def __warn(self, msg: str):
        ''' Log a warning message. '''
        self.__logger.warning(msg)
    
    def __error(self, msg: str):
        ''' Log an error message. '''
        self.__logger.error(msg)

    def __get_tmp_file_path(self):
        ''' Get the path to the temporary file. '''
        return '/tmp/bbdc_captcha.png'

    def solve_captcha(self, captcha_type: str, tries: int = 10):
        ''' Attempt to pass the captcha, returning the captcha data and token. '''
        assert captcha_type in ['login', 'booking']
        self.__info(f'Solving captcha..., type: {captcha_type}, tries: {tries}.')
        login_captcha_url = 'https://booking.bbdc.sg/bbdc-back-service/api/auth/getLoginCaptchaImage'
        booking_captcha_url = 'https://booking.bbdc.sg/bbdc-back-service/api/booking/manage/getCaptchaImage'
        for i in range(tries):
            self.__info('Captcha attempt #' + str(i + 1))
            # get captcha image and save to disk
            if captcha_type == 'login':
                res = requests.post(login_captcha_url, headers=self.headers).json()
            else:
                res = self.post_signed(booking_captcha_url, {})
            if not res['success']:
                self.__warn('Failed to get captcha. Error: ' + res['message'])
                continue
            data = res['data']
            base64_image = data['image']
            with open(self.__get_tmp_file_path(), 'wb') as f:
                f.write(base64.b64decode(base64_image.replace('data:image/png;base64,', '')))
            # solve captcha
            answer = self.__ocr_solver.solve(self.__get_tmp_file_path())
            if len(answer) != 5:
                self.__warn('Improper captcha answer: ' + answer)
                continue
            data['answer'] = answer
            self.__info('Captcha solved (probably).')
            del data['image']
            self.__debug(pformat(data, indent=4))
            return data
        self.__error('Failed to solve captcha.')

    def authenticate(self, username: str, password: str, tries: int = 10):
        ''' Authenticate to the website. '''
        self.__info(f'Authenticating..., username: {username}, tries: {tries}.')
        login_url = 'https://booking.bbdc.sg/bbdc-back-service/api/auth/login'
        for i in range(tries):
            self.__info('Authenticate attempt #' + str(i + 1))
            # solve captcha
            captcha_data = self.solve_captcha('login')
            # authenticate
            payload = {
                'captchaToken': captcha_data['captchaToken'],
                'userId': username,
                'userPass': password,
                'verifyCodeId': captcha_data['verifyCodeId'],
                'verifyCodeValue': captcha_data['answer']
            }
            res = requests.post(login_url, headers=self.headers, json=payload).json()
            if not res['success']:
                self.__warn('Failed to authenticate. Error: ' + res['message'])
                continue
            self.authorization_token = res['data']['tokenContent']
            self.__info('Successfully authenticated as ' + res['data']['username'])
            # save credentials for reauthentication
            self.saved_username = username
            self.saved_password = password
            # get course authorization token
            self.get_course_authorization_token()
            return res['data']['username']
        return None
        
    def get_course_authorization_token(self):
        self.__info('Getting course authorization token...')
        url = 'https://booking.bbdc.sg/bbdc-back-service/api/account/listAccountCourseType'
        payload = {}
        res = self.post_signed(url, payload)
        if not res['success']:
            self.__error('Failed to get course authorization token. Error: ' + res['message'])
            return
        self.course_authorization_token = res['data']['activeCourseList'][0]['authToken']
        self.__info('Successfully got course authorization token.')
    
    def reauthenticate(self):
        ''' Reauthenticate using saved credentials. '''
        self.__info('Reauthenticating...')
        if self.saved_username == '' or self.saved_password == '':
            raise Exception('No saved credentials to reauthenticate.')
        self.authenticate(self.saved_username, self.saved_password)
       
    def post_signed(self, url: str, data: dict) -> dict:
        ''' Post data to a signed endpoint. '''
        self.__info(f'POST {url}')
        headers = self.headers.copy()
        headers['authorization'] = self.authorization_token
        headers['jsessionid'] = self.course_authorization_token
        cookies = {
            'bbdc-token': self.authorization_token.replace(' ', '%20')
        }
        response = requests.post(url, headers=headers, json=data, cookies=cookies)
        self.__debug(pformat(response, indent=4))
        self.__debug(pformat(response.json(), indent=4))
        if response.status_code == 402:
            self.__info('Session expired. Re-authenticating...')
            self.reauthenticate()
            # retry request
            return self.post_signed(url, data)
        return response.json()

    def api_list_c3_practical_slot_released(self, month: str = None):
        ''' List all C3 practical trainings. '''
        url = 'https://booking.bbdc.sg/bbdc-back-service/api/booking/c3practical/listC3PracticalSlotReleased'
        data = {
            "courseType": "3A",
            "insInstructorId": "",
            "releasedSlotMonth": month,
            "stageSubDesc": "Practical slot",
            "subVehicleType": None,
            "subStageSubNo": None,
        }
        return self.post_signed(url, data)
    
    def get_available_practical_slots(self, maximum_months_into_future: int = 3):
        ''' Check for available practical slots. '''
        self.__info(f'Checking for available practical slots, maximum months into future: {maximum_months_into_future}.')
        all_slots = []
        for i in range(maximum_months_into_future):
            self.__info(f'Checking {i} months into the future...')
            month = (datetime.now() + relativedelta(months=i)).strftime('%Y%m')
            res = self.api_list_c3_practical_slot_released(month)
            if not res['success']:
                self.__error('Failed to check available slots. Error: ' + res['message'])
                continue
            slots = res['data']['releasedSlotListGroupByDay']
            if slots is None:
                self.__info(f'No slots found in {month}.')
                continue
            slots = [Slot.from_dict(slot) for slot in sum(slots.values(), start=[])]
            slots = [slot for slot in slots if slot.is_available()]
            all_slots += slots
            self.__info(f'Found {len(slots)} slots in {month}:')
            self.__debug(pformat(slots, indent=4))
        return all_slots
    
    def api_book_c3_practical_slot(self, captcha_data: dict, slot: Slot):
        url = 'https://booking.bbdc.sg/bbdc-back-service/api/booking/c3practical/bookC3PracticalSlot'
        data = {
            'verifyCodeId': captcha_data['verifyCodeId'],
            'verifyCodeValue': captcha_data['answer'],
            'captchaToken': captcha_data['captchaToken'],
            'courseType': '3A',
            'cacheId': '', # a unique id to each type of booking, from listC3PracticalTrainings
            'slotIdList': [slot.slotId],
            'encryptSlotList': [
                {
                    'slotIdEnc': slot.slotIdEnc,
                    'bookingProgressEnc': slot.bookingProgressEnc
                }
            ]
        }
        return self.post_signed(url, data)
    
    def book_practical_slot(self, slot: Slot):
        ''' Book a practical slot. '''
        self.__info(f'Booking slot: {pformat(slot, indent=4)}.')
        # solve captcha
        captcha_data = self.solve_captcha('booking')
        # book slot
        res = self.api_book_c3_practical_slot(captcha_data, slot)
        if not res['success']:
            self.__error('Failed to book slot. Error: ' + res['message'])
            return False
        self.__info('Successfully booked slot.')
        return True
    
    def api_list_booked_c3_practical_slots(self, month: str = None):
        url = 'https://booking.bbdc.sg/bbdc-back-service/api/booking/manage/listAllPracticalBooking'
        data = {
            'courseType': '3A'
        }
        return self.post_signed(url, data)
    
    def get_all_booked_slots(self):
        ''' Get all booked slots. '''
        self.__info('Getting all booked slots...')
        res = self.api_list_booked_c3_practical_slots()
        if not res['success']:
            self.__error('Failed to get all booked slots. Error: ' + res['message'])
            return []
        slots = [BookedSlot.from_dict(slot) for slot in res['data']['theoryActiveBookingList']]
        self.__info(f'Got {len(slots)} booked slots:')
        self.__debug(pformat(slots, indent=4))
        return slots
    
    def api_cancel_c3_practical_slot(self, slot: BookedSlot):
        url = 'https://booking.bbdc.sg/bbdc-back-service/api/booking/manage/cancelBooking'
        data = {
            'bookingId': slot.bookingId,
            'theoryType': slot.theoryType,
            'manageType': slot.dataType,
        }
        return self.post_signed(url, data)
    
    def cancel_practical_slot(self, slot: BookedSlot):
        ''' Cancel a practical slot. '''
        self.__info(f'Cancelling slot: {pformat(slot, indent=4)}.')
        res = self.api_cancel_c3_practical_slot(slot)
        if not res['success']:
            self.__error('Failed to cancel slot. Error: ' + res['message'])
            return False
        self.__info('Successfully cancelled slot.')
        return True