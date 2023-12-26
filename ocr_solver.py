import cv2
import subprocess
import pytesseract
import re

class OCRSolver:

    def __init__(self):
        pass

    def __apply_ridge_thinning(self, image_path: str):
        ''' Apply ridge thinning to the image. '''
        original_img_file = image_path
        tmp_img_file = '/tmp/bbdc_captcha_tmp.png'
        command = f'convert {original_img_file} -colorspace gray -separate -average -threshold 90% -negate -morphology Thinning "Ridges" {tmp_img_file}'
        subprocess.run(command, shell=True)
        return tmp_img_file
    
    def __apply_gaussian_threshold(self, image_path: str):
        ''' Apply gaussian threshold to the image. '''
        img = cv2.imread(image_path)
        for i in range(2):
            img = cv2.threshold(cv2.GaussianBlur(img, (5, 7), 0), 140, 255, cv2.THRESH_BINARY)[1]
        return img

    def __get_text(self, img):
        ''' Use pytesseract to get text from the image. '''
        text = pytesseract.image_to_string(img, lang='eng', config='--psm 8')
        text = re.sub(r'[^\w]', '', text)
        return text

    def solve(self, image_path):
        ''' Solve the captcha, returning the text. '''
        thinned = self.__apply_ridge_thinning(image_path)
        img = self.__apply_gaussian_threshold(thinned)
        text = self.__get_text(img)
        return text
