# -*- coding:utf-8 -*-
import os
import re
import rsa
import sys
import json
import time
import base64
import random
import signal
import hashlib
import logging
import sqlite3
import datetime
import requests
import threading
import websocket
import logging.handlers
import ThirdParty.muggle_ocr as muggle_ocr
from flask import Flask, request, make_response

# 数据库地址
DB_PATH = "./ClassSchedule.db"

# WebSocket 监听地址
WS_LISTEN_URL = "ws://127.0.0.1:QAQ/"

# 顶象验证码鉴权 (压测时瓶颈是SSL加解密部分，改用 http 连接可以处理更多请求)
DX_APP_ID = ""
DX_APP_SECRET = ""
CAPTCHA_URL = "https://proxy-api.dingxiang-inc.com/api/tokenVerify"

# 加密存储密码
pubkey = rsa.PublicKey.load_pkcs1(
    b"-----BEGIN RSA PUBLIC KEY-----\nQAQ\n-----END RSA PUBLIC KEY-----\n"
)
privkey = rsa.PrivateKey.load_pkcs1(
    b"\n-----BEGIN RSA PRIVATE KEY-----\nQAQ\n-----END RSA PRIVATE KEY-----\n"
)

# 爬虫使用的代理
proxies = {
    "http": "socks5://127.0.0.1:QAQ",
    "https": "socks5://127.0.0.1:QAQ",
}

# Flask的密钥 (未使用)
app = Flask(__name__)
app.config["SECRET_KEY"] = "QAQ"


exit_signal = False


class Crawler:
    sdk = muggle_ocr.SDK(model_type=muggle_ocr.ModelType.Captcha)

    @staticmethod
    def getCpatcha(session, firstGet):
        captchaHeader = {
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN",
            "Cache-Control": "no-cache",
            "Connection": "Keep-Alive",
            "Host": "ea.ccut.edu.cn",
            "Pragma": "no-cache",
            "Referer": "http://ea.ccut.edu.cn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; Touch; rv:11.0) like Gecko",
        }
        captchaCnt = 0
        while True:
            if captchaCnt > 5:  # 超过重试次数，返回None
                return None

            captchaUrl = "http://ea.ccut.edu.cn/verifycode.servlet"
            if not firstGet:
                captchaUrl += "?" + str(random.random())

            res = session.get(url=captchaUrl, headers=captchaHeader)
            if res.status_code != 200:  # 请求状态码异常，重试
                captchaCnt += 1
                firstGet = False
                logger.warning("请求状态码异常，重试")
                continue

            timea = time.time()
            text = Crawler.sdk.predict(image_bytes=res.content)
            logger.debug("time: " + str(time.time() - timea))
            # with open("./CaptchaImgs/tmp.jpg", "wb") as f:
            #     f.write(res.content)
            logger.debug("captcha predict = " + text)

            if len(text) < 4:  # 长度不符，重试
                captchaCnt += 1
                firstGet = False
                continue
            else:
                return text[0:4]

    @staticmethod
    def login(session, username, password):
        loginHeader = {
            "Accept": "text/html, application/xhtml+xml, image/jxr, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN",
            "Cache-Control": "no-cache",
            "Connection": "Keep-Alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "ea.ccut.edu.cn",
            "Origin": "http://ea.ccut.edu.cn",
            "Referer": "http://ea.ccut.edu.cn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; Touch; rv:11.0) like Gecko",
        }
        loginSSOHeader = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "*/*",
            "Cache-Control": "no-cache",
            "Connection": "Keep-Alive",
            "Content-Length": "0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "ea.ccut.edu.cn",
            "Referer": "http://ea.ccut.edu.cn/framework/main.jsp",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; Touch; rv:11.0) like Gecko",
        }
        loginSuccessBody = b"<script language='javascript'>window.location.href='http://ea.ccut.edu.cn/framework/main.jsp';</script>\r\n"
        retryCnt = 0
        otherMaxRetry = 3
        captchaMaxRetry = 10
        while otherMaxRetry > 0 and captchaMaxRetry > 0 and retryCnt < 20:
            retryCnt += 1
            # session.get("http://ea.ccut.edu.cn/", headers=loginHeader)
            captcha = Crawler.getCpatcha(session, (retryCnt > 1))
            if captcha is None:
                captchaMaxRetry -= 1
                continue
            login_form = (
                "USERNAME={}&PASSWORD={}&useDogCode=&RANDOMCODE={}&x={}&y={}".format(
                    username,
                    password,
                    captcha,
                    str(random.randint(1, 61)),
                    str(random.randint(1, 22)),
                )
            )
            try:
                res = session.post(
                    url="http://ea.ccut.edu.cn/Logon.do?method=logon",
                    headers=loginHeader,
                    data=login_form,
                )
            except Exception as e:
                otherMaxRetry -= 1
                captchaMaxRetry = 10
                logger.exception(e)
            if res.status_code == 200:
                if res.content == loginSuccessBody:
                    try:
                        session.post(
                            url="http://ea.ccut.edu.cn/Logon.do?method=logonBySSO",
                            headers=loginSSOHeader,
                        )
                        return "success"
                    except Exception as e:
                        otherMaxRetry -= 1
                        captchaMaxRetry = 10
                        logger.exception(e)
                else:
                    errInfo = re.search(
                        '<font color=red><span id="errorinfo">(.*)?</span>',
                        res.content.decode("utf-8"),
                    )
                    if errInfo is not None:
                        if errInfo.group(1) == "验证码错误!!":
                            captchaMaxRetry -= 1
                        else:
                            return errInfo.group(1)
            else:
                otherMaxRetry -= 1
                captchaMaxRetry = 10
            time.sleep(random.randint(1, 5) / 10)
        return "[err]network error"

    @staticmethod
    def getCourseList(session):
        timeStr = str(int(time.time())) + "000"
        courses = {
            "mon": {
                "class1": [],
                "class2": [],
                "class3": [],
                "class4": [],
                "class5": [],
            },
            "tue": {
                "class1": [],
                "class2": [],
                "class3": [],
                "class4": [],
                "class5": [],
            },
            "wed": {
                "class1": [],
                "class2": [],
                "class3": [],
                "class4": [],
                "class5": [],
            },
            "thu": {
                "class1": [],
                "class2": [],
                "class3": [],
                "class4": [],
                "class5": [],
            },
            "fri": {
                "class1": [],
                "class2": [],
                "class3": [],
                "class4": [],
                "class5": [],
            },
            "sat": {
                "class1": [],
                "class2": [],
                "class3": [],
                "class4": [],
                "class5": [],
            },
            "sun": {
                "class1": [],
                "class2": [],
                "class3": [],
                "class4": [],
                "class5": [],
            },
            "note": {"noteStr": "", "noteClass": []},
        }
        day2week = {
            1: "mon",
            2: "tue",
            3: "wed",
            4: "thu",
            5: "fri",
            6: "sat",
            7: "sun",
        }
        day2class = {1: "class1", 2: "class2", 3: "class3", 4: "class4", 5: "class5"}
        courseListHeader = {
            "Accept": "text/html, application/xhtml+xml, image/jxr, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN",
            "Connection": "Keep-Alive",
            "Host": "ea.ccut.edu.cn",
            "Referer": "http://ea.ccut.edu.cn/framework/new_window.jsp?lianjie=&winid=win1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; Touch; rv:11.0) like Gecko",
        }
        courseHeader = {
            "Accept": "text/html, application/xhtml+xml, image/jxr, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN",
            "Connection": "Keep-Alive",
            "Host": "ea.ccut.edu.cn",
            "Referer": "http://ea.ccut.edu.cn/tkglAction.do?method=kbxxXs&tktime="
            + timeStr,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; Touch; rv:11.0) like Gecko",
        }
        courseListUrl = (
            "http://ea.ccut.edu.cn/tkglAction.do?method=kbxxXs&tktime=" + timeStr
        )
        try:
            courseList = session.get(url=courseListUrl, headers=courseListHeader)
            iframe = re.search(
                '<IFRAME\s+frameBorder="0"\s+id="fcenter"\s+name="fcenter"\s+src="/tkglAction.do\?method=goListKbByXs(.*)?"',
                courseList.content.decode("utf-8"),
            )
            if not iframe:
                return False
            courseUrl = (
                "http://ea.ccut.edu.cn/tkglAction.do?method=goListKbByXs"
                + iframe.group(1)
            )
            # courseUrl = 'http://ea.ccut.edu.cn/tkglAction.do?method=goListKbByXs&istsxx=no&xnxqh=2018-2019-2&zc=&xs0101id='
            print(courseUrl)
            course = session.get(url=courseUrl, headers=courseHeader)
            # with open("./kebiao3.html", "wb") as f:
            #     f.write(course.content)
            classHTML = course.content.decode("utf-8")
            # print(course.content.decode("utf-8"))

            # 处理备注
            note = courseStr = re.search(
                '<td   height="28" colspan="7"  align="center">\s+&nbsp; (.*)\r\n',
                classHTML,
            )
            if note and (len(note.group(1)) > 0):
                noteStr = note.group(1)
                # print(str(len(noteStr)) + '"' + noteStr + '"')
                courseDataList = noteStr.split(";")
                for courseData in courseDataList:
                    # print(courseData)
                    logger.info(courseData)
                    courseData = re.sub("^\\s+", "", courseData)
                    courseData = re.sub("\\s+$", "", courseData)
                    courseOne = re.search("(.*?)\s+(.*?)\s+(.*?)$", courseData)
                    if courseOne and (len(courseOne.groups()) == 3):
                        courseInfo = {
                            "name": courseOne.group(1),
                            "teacher": courseOne.group(2),
                            "weekStr": courseOne.group(3),
                            "week": [],
                            "place": "",
                        }
                        courseTimeList = courseOne.group(3).split(",")
                        for timeRange in courseTimeList:
                            timeList = re.search("(\d+)-(\d+)", timeRange)
                            if timeList and (len(timeList.groups()) == 2):
                                timeStart = timeList.group(1)
                                timeEnd = timeList.group(2)
                                for j in range(int(timeStart), int(timeEnd) + 1):
                                    courseInfo["week"].append(j)
                            else:
                                courseInfo["week"].append(int(timeRange))
                        courses["note"]["noteClass"].append(courseInfo)
                        courses["note"]["noteStr"] += "{} ({}) {}周; ".format(
                            courseInfo["name"],
                            courseInfo["teacher"],
                            courseInfo["weekStr"],
                        )
            # 处理课程
            classHTML = re.sub("&nbsp;", "", classHTML)
            for dayOfWeek in range(1, 8):
                for section in range(1, 6):
                    regexStr = (
                        '<div id="{}-{}-2" style="display: none;">(.*)</div>'.format(
                            section, dayOfWeek
                        )
                    )
                    courseStr = re.search(regexStr, classHTML)
                    if courseStr:
                        courseDataList = re.findall("(.*?)<br>", courseStr.group(1))
                        infoLen = len(courseDataList)
                        for i in range(infoLen):
                            courseDataList[i] = re.sub("\s+", "", courseDataList[i])
                        i = 0
                        while i < infoLen:
                            courseTime = re.search(
                                "<nobr>(.*?)周<nobr>", courseDataList[i + 3]
                            ).group(1)
                            courseInfo = {
                                "name": courseDataList[i],
                                "teacher": courseDataList[i + 2],
                                "weekStr": courseTime,
                                "week": [],
                                "place": courseDataList[i + 4],
                            }
                            courseTimeList = courseTime.split(",")
                            for timeRange in courseTimeList:
                                timeList = re.search("(\d+)-(\d+)", timeRange)
                                if timeList:
                                    timeStart = timeList.group(1)
                                    timeEnd = timeList.group(2)
                                    for j in range(int(timeStart), int(timeEnd) + 1):
                                        courseInfo["week"].append(j)
                                else:
                                    courseInfo["week"].append(int(timeRange))
                            courses[day2week[dayOfWeek]][day2class[section]].append(
                                courseInfo
                            )
                            i += 5
                    else:
                        courseDataList = []
            return courses
        except Exception as e:
            logger.error(e)
            return False

    @staticmethod
    def buildHtml(sid, userID, courses):
        if userID is None:
            return
        id2chn = ["一", "二", "三", "四", "五"]
        class2id = ["class1", "class2", "class3", "class4", "class5"]
        day2id = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        html = [
            """<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="X-UA-Compatible" content="IE=edge"><title>""",
            str(sid),
            """的课程表</title><meta name="viewport" content="width=device-width,initial-scale=1" style="display:none"><style>/*! tailwindcss v3.0.23 | MIT License | https://tailwindcss.com*/*,:after,:before{box-sizing:border-box;border:0 solid #e5e7eb}:after,:before{--tw-content:""}html{line-height:1.5;-webkit-text-size-adjust:100%;-moz-tab-size:4;-o-tab-size:4;tab-size:4;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica Neue,Arial,Noto Sans,sans-serif,Apple Color Emoji,Segoe UI Emoji,Segoe UI Symbol,Noto Color Emoji}body{margin:0;line-height:inherit}hr{height:0;color:inherit;border-top-width:1px}abbr:where([title]){-webkit-text-decoration:underline dotted;text-decoration:underline dotted}h1,h2,h3,h4,h5,h6{font-size:inherit;font-weight:inherit}a{color:inherit;text-decoration:inherit}b,strong{font-weight:bolder}code,kbd,pre,samp{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,Liberation Mono,Courier New,monospace;font-size:1em}small{font-size:80%}sub,sup{font-size:75%;line-height:0;position:relative;vertical-align:initial}sub{bottom:-.25em}sup{top:-.5em}table{text-indent:0;border-color:inherit;border-collapse:collapse}button,input,optgroup,select,textarea{font-family:inherit;font-size:100%;line-height:inherit;color:inherit;margin:0;padding:0}button,select{text-transform:none}[type=button],[type=reset],[type=submit],button{-webkit-appearance:button;background-color:initial;background-image:none}:-moz-focusring{outline:auto}:-moz-ui-invalid{box-shadow:none}progress{vertical-align:initial}::-webkit-inner-spin-button,::-webkit-outer-spin-button{height:auto}[type=search]{-webkit-appearance:textfield;outline-offset:-2px}::-webkit-search-decoration{-webkit-appearance:none}::-webkit-file-upload-button{-webkit-appearance:button;font:inherit}summary{display:list-item}blockquote,dd,dl,figure,h1,h2,h3,h4,h5,h6,hr,p,pre{margin:0}fieldset{margin:0}fieldset,legend{padding:0}menu,ol,ul{list-style:none;margin:0;padding:0}textarea{resize:vertical}input::-moz-placeholder,textarea::-moz-placeholder{opacity:1;color:#9ca3af}input:-ms-input-placeholder,textarea:-ms-input-placeholder{opacity:1;color:#9ca3af}input::placeholder,textarea::placeholder{opacity:1;color:#9ca3af}[role=button],button{cursor:pointer}:disabled{cursor:default}audio,canvas,embed,iframe,img,object,svg,video{display:block;vertical-align:middle}img,video{max-width:100%;height:auto}[hidden]{display:none}*,:after,:before{--tw-translate-x:0;--tw-translate-y:0;--tw-rotate:0;--tw-skew-x:0;--tw-skew-y:0;--tw-scale-x:1;--tw-scale-y:1;--tw-pan-x: ;--tw-pan-y: ;--tw-pinch-zoom: ;--tw-scroll-snap-strictness:proximity;--tw-ordinal: ;--tw-slashed-zero: ;--tw-numeric-figure: ;--tw-numeric-spacing: ;--tw-numeric-fraction: ;--tw-ring-inset: ;--tw-ring-offset-width:0px;--tw-ring-offset-color:#fff;--tw-ring-color:#3b82f680;--tw-ring-offset-shadow:0 0 #0000;--tw-ring-shadow:0 0 #0000;--tw-shadow:0 0 #0000;--tw-shadow-colored:0 0 #0000;--tw-blur: ;--tw-brightness: ;--tw-contrast: ;--tw-grayscale: ;--tw-hue-rotate: ;--tw-invert: ;--tw-saturate: ;--tw-sepia: ;--tw-drop-shadow: ;--tw-backdrop-blur: ;--tw-backdrop-brightness: ;--tw-backdrop-contrast: ;--tw-backdrop-grayscale: ;--tw-backdrop-hue-rotate: ;--tw-backdrop-invert: ;--tw-backdrop-opacity: ;--tw-backdrop-saturate: ;--tw-backdrop-sepia: }.absolute{position:absolute}.top-\[-100vw\]{top:-100vw}.left-0{left:0}.inline-block{display:inline-block}.table{display:table}.h-\[100vw\]{height:100vw}.w-\[100vh\]{width:100vh}.w-full{width:100%}.min-w-full{min-width:100%}.origin-bottom-left{transform-origin:bottom left}.rotate-90{--tw-rotate:90deg;transform:translate(var(--tw-translate-x),var(--tw-translate-y)) rotate(var(--tw-rotate)) skewX(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y))}.divide-y>:not([hidden])~:not([hidden]){--tw-divide-y-reverse:0;border-top-width:calc(1px*(1 - var(--tw-divide-y-reverse)));border-bottom-width:calc(1px*var(--tw-divide-y-reverse))}.divide-x>:not([hidden])~:not([hidden]){--tw-divide-x-reverse:0;border-right-width:calc(1px*var(--tw-divide-x-reverse));border-left-width:calc(1px*(1 - var(--tw-divide-x-reverse)))}.divide-gray-200>:not([hidden])~:not([hidden]){--tw-divide-opacity:1;border-color:rgb(229 231 235/var(--tw-divide-opacity))}.overflow-auto{overflow:auto}.whitespace-nowrap{white-space:nowrap}.rounded-lg{border-radius:.5rem}.border{border-width:1px}.border-x-2{border-left-width:2px;border-right-width:2px}.border-gray-200{--tw-border-opacity:1;border-color:rgb(229 231 235/var(--tw-border-opacity))}.bg-gray-50{--tw-bg-opacity:1;background-color:rgb(249 250 251/var(--tw-bg-opacity))}.bg-white{--tw-bg-opacity:1;background-color:rgb(255 255 255/var(--tw-bg-opacity))}.px-2{padding-left:.5rem;padding-right:.5rem}.py-2{padding-top:.5rem;padding-bottom:.5rem}.px-1{padding-left:.25rem;padding-right:.25rem}.py-3{padding-top:.75rem;padding-bottom:.75rem}.px-3{padding-left:.75rem;padding-right:.75rem}.px-0{padding-left:0;padding-right:0}.text-center{text-align:center}.align-middle{vertical-align:middle}.font-sans{font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica Neue,Arial,Noto Sans,sans-serif,Apple Color Emoji,Segoe UI Emoji,Segoe UI Symbol,Noto Color Emoji}.text-sm{font-size:.875rem;line-height:1.25rem}.font-medium{font-weight:500}.tracking-wider{letter-spacing:.05em}.text-gray-500{--tw-text-opacity:1;color:rgb(107 114 128/var(--tw-text-opacity))}.text-gray-900{--tw-text-opacity:1;color:rgb(17 24 39/var(--tw-text-opacity))}.shadow{--tw-shadow:0 1px 3px 0 #0000001a,0 1px 2px -1px #0000001a;--tw-shadow-colored:0 1px 3px 0 var(--tw-shadow-color),0 1px 2px -1px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow,0 0 #0000),var(--tw-ring-shadow,0 0 #0000),var(--tw-shadow)}@media (min-width:1024px){.lg\:relative{position:relative}.lg\:top-0{top:0}.lg\:h-auto{height:auto}.lg\:w-auto{width:auto}.lg\:rotate-0{--tw-rotate:0deg;transform:translate(var(--tw-translate-x),var(--tw-translate-y)) rotate(var(--tw-rotate)) skewX(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y))}}</style></head><body class="font-sans"><div id="wrapper" class="min-w-full overflow-auto px-2 py-2 align-middle inline-block"><div class="min-w-full shadow border-gray-200 rounded-lg"><table class="w-full divide-y divide-gray-200 border-1 rounded-lg"><thead class="bg-gray-50"><tr><th class="px-1 py-3 text-center text-sm font-medium text-gray-500 tracking-wider whitespace-nowrap border"></th><th class="px-1 py-3 text-center text-sm font-medium text-gray-500 tracking-wider whitespace-nowrap border">星期一</th><th class="px-1 py-3 text-center text-sm font-medium text-gray-500 tracking-wider whitespace-nowrap border">星期二</th><th class="px-1 py-3 text-center text-sm font-medium text-gray-500 tracking-wider whitespace-nowrap border">星期三</th><th class="px-1 py-3 text-center text-sm font-medium text-gray-500 tracking-wider whitespace-nowrap border">星期四</th><th class="px-1 py-3 text-center text-sm font-medium text-gray-500 tracking-wider whitespace-nowrap border">星期五</th><th class="px-1 py-3 text-center text-sm font-medium text-gray-500 tracking-wider whitespace-nowrap border">星期六</th><th class="px-1 py-3 text-center text-sm font-medium text-gray-500 tracking-wider whitespace-nowrap border">星期日</th></tr></thead><tbody class="bg-white divide-y divide-gray-200">""",
        ]
        for classID in range(0, 5):
            html.append(
                '<tr><td class="px-2 py-2 text-center text-sm font-medium text-gray-500 tracking-wider bg-gray-50 border">第<br>'
            )
            html.append(id2chn[classID])
            html.append("<br>大<br>节</td>")
            for day in range(0, 7):
                html.append(
                    '<td class="px-3 py-2 text-sm text-center font-medium text-gray-900 border divide-y">'
                )
                courseList = courses[day2id[day]][class2id[classID]]
                for course in courseList:
                    html.append(
                        '<div class="py-2">{}<br><a class="whitespace-nowrap">({})&nbsp;&nbsp;{}周</a><br><a class="whitespace-nowrap">{}</a></div>'.format(
                            course["name"],
                            course["teacher"],
                            course["weekStr"],
                            course["place"],
                        )
                    )
                html.append("</td>")
            html.append("</tr>")
        # 备注部分
        html.append(
            '<tr><td class="px-2 py-2 text-center text-sm font-medium text-gray-500 tracking-wider bg-gray-50 border">备注</td><td colspan="7"><table class="w-full"><thead></thead><tbody class="bg-white divide-gray-200 "><tr>'
        )
        noteLen = len(courses["note"]["noteClass"])
        for i in range(noteLen):
            course = courses["note"]["noteClass"][i]
            if i == 1 or (i + 1 == noteLen):
                html.append(
                    '<td class="px-0 py-2 text-sm text-center font-medium text-gray-900"><a class="whitespace-nowrap">{}</a> <a class="whitespace-nowrap">({})</a> <a class="whitespace-nowrap">{}周</a></td>'.format(
                        course["name"], course["teacher"], course["weekStr"]
                    )
                )
            else:
                html.append(
                    '<td class="px-0 py-2 text-sm text-center font-medium text-gray-900 border-x-2 divide-x"><a class="whitespace-nowrap">{}</a> <a class="whitespace-nowrap">({})</a> <a class="whitespace-nowrap">{}周</a></td>'.format(
                        course["name"], course["teacher"], course["weekStr"]
                    )
                )
        html.append(
            "</tr></tbody></table></td></tr></tbody></table></div></div></body></html>"
        )

        try:
            with open("./Pages/{}.html".format(userID), "wb") as f:
                f.write("".join(html).encode("utf-8"))
        except Exception as e:
            logger.exception(e)


class User:
    captcha_session = requests.Session()

    @staticmethod
    def encrypt_password(password):
        message = password.encode("ascii")
        crypto = rsa.encrypt(message, pubkey)
        crypto_str = base64.b64encode(crypto).decode("ascii")
        return crypto_str

    @staticmethod
    def decrypt_password(crypto_str):
        decrypto = base64.b64decode(crypto_str)
        password = rsa.decrypt(decrypto, privkey).decode("ascii")
        return password

    @staticmethod
    def randStr(chars="ABCDEFGHJKMPQRTWXY2346789", N=15):
        return "".join(random.choice(chars) for _ in range(N))

    @staticmethod
    def getNewUserID(conn):
        c = conn.cursor()
        try:
            while True:
                userID = User.randStr()
                c.execute("SELECT * FROM courses WHERE userID = ?", (userID,))
                if not c.fetchone():
                    break
        except Exception as e:
            logger.error(e)
        finally:
            c.close()
        return userID

    @staticmethod
    def checkSid(sid):
        sid_pattern = re.compile("^20\d{6}$")
        return not (sid_pattern.match(str(sid)) is None)

    @staticmethod
    def checkCaptcha(token):
        # return True
        if token == "" or (token is None) or len(token) > 1024:
            return False
        else:
            arr = token.split(":")
            constId = ""
            if len(arr) == 2:
                constId = arr[1]
            sign = hashlib.md5(
                (DX_APP_SECRET + arr[0] + DX_APP_SECRET).encode("ascii")
            ).hexdigest()
            req_url = (
                CAPTCHA_URL
                + "?appKey="
                + DX_APP_ID
                + "&token="
                + arr[0]
                + "&constId="
                + constId
                + "&sign="
                + sign
            )
            try:
                res = User.captcha_session.get(url=req_url, timeout=2)
                if res.status_code != 200:
                    logger.info("验证码校验失败: " + str(res.status_code))
                    return False
                result = res.json()
                logger.info("验证码校验: " + str(result))
                return result["success"]
            except Exception as e:
                logger.exception(e)
                return False


class ApiServerThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

        from werkzeug.serving import WSGIRequestHandler

        def address_string(self):
            return "[%s]" % (self.headers.get("X-Real-Ip", self.client_address[0]))

        WSGIRequestHandler.address_string = address_string

        logging.basicConfig(
            level=logging.DEBUG,
            format="[Thread %(thread)d] %(levelname)s %(asctime)s "
            "[message: %(message)s] "
            "%(funcName)s[line:%(lineno)d]",
            datefmt="%Y-%m-%d %H:%M:%S",
            filemode="a",
        )

    @app.route("/api/getCurriculum", methods=["POST"])
    def getCurriculum():
        res_code = 5
        res_msg = "未知错误！"
        try:
            sid = request.json.get("sid")
            password = request.json.get("password")
            captcha = request.json.get("captcha")
            logger.info("查询请求: sid = " + sid)
            if not User.checkSid(sid):
                logger.info("查询失败: sid = " + sid + "(学号格式不正确)")
                res_code = 1
                res_msg = "账号不存在！"
            elif not User.checkCaptcha(captcha):
                logger.info("查询失败: sid = " + sid + "(验证码校验错误)")
                res_code = 2
                res_msg = "验证码校验错误，请重试！"
            else:
                conn = sqlite3.connect(DB_PATH)
                c2 = conn.cursor()
                try:
                    cursor = c2.execute("SELECT userID FROM courses WHERE sid = " + sid)
                    userID = cursor.fetchone()
                    if userID is None:
                        res = updateCourse(conn, sid, password)
                        if res == "success":
                            cursor = c2.execute(
                                "SELECT userID FROM courses WHERE sid = " + sid
                            )
                            newUserID = cursor.fetchone()
                            if newUserID is None:
                                res_code = 3
                                res_msg = "未知错误！"
                            else:
                                res_code = 0
                                res_msg = str(newUserID[0])
                        else:
                            res_code = 3
                            res_msg = res
                    else:
                        res_code = 0
                        res_msg = str(userID[0])

                except Exception as e:
                    pass
                c2.close()
                conn.close()
        except Exception as e:
            logger.info("查询错误: " + request.get_data().decode("utf-8"))
            logger.info(e)
        body = {"code": res_code, "message": res_msg}
        response = make_response(body)
        response.headers["content-type"] = "application/json"
        return response, 200

    def run(self):
        logger.info("Flask线程开启")
        app.run(debug=False, threaded=True, port=5001)
        logger.info("Flask线程退出")


class WsHandler:
    @staticmethod
    def onWebsocketMessage(ws, message):
        try:
            data = json.loads(message)
            logger.info(data)
        except Exception as e:
            logger.exception(e)
            return

        try:
            conn = sqlite3.connect(DB_PATH)
            res = updateCourse(conn, data["username"], data["password"])
            if res == "success":
                ws.send(
                    json.dumps(
                        {
                            "QQ": data["QQ"],
                            "username": data["username"],
                            "status": True,
                            "reason": "成功",
                        }
                    )
                )
            else:
                ws.send(
                    json.dumps(
                        {
                            "QQ": data["QQ"],
                            "username": data["username"],
                            "status": False,
                            "reason": res,
                        }
                    )
                )
        except Exception as e:
            ws.send(json.dumps({"id": data["id"], "status": "updateErr"}))
            logger.error(message)
            logger.exception(e)
        finally:
            conn.close()

    @staticmethod
    def onWebsocketError(ws, error):
        logger.error(error)

    @staticmethod
    def onWebsocketClose(ws, code, reason):
        logger.warning("### Websocket closed ###")
        if exit_signal:
            return
        time.sleep(0.3)
        ws = websocket.WebSocketApp(
            WS_LISTEN_URL,
            on_message=WsHandler.onWebsocketMessage,
            on_error=WsHandler.onWebsocketError,
            on_close=WsHandler.onWebsocketClose,
        )
        logger.warning("### Websocket started ###")
        ws.run_forever(ping_interval=60, ping_timeout=5)


def updateCourse(conn, username, password):
    logger.info("正在更新 " + username + " 的课表")
    session = requests.Session()
    if len(sys.argv) >= 3 and sys.argv[2] == "proxy":
        session.proxies = proxies
    try:
        loginRes = Crawler.login(session, username, password)
        if loginRes == "success":
            courseDataJ = Crawler.getCourseList(session)
            if courseDataJ:
                courseData = json.dumps(courseDataJ)
                c2 = conn.cursor()
                status = "[err]storage course data error"
                try:
                    timeStr = time.strftime("%m/%d %H:%M:%S", time.localtime())
                    cursor = c2.execute(
                        "SELECT userID FROM courses WHERE sid = " + username
                    )
                    userID = cursor.fetchone()
                    if userID is None:
                        newUserID = User.getNewUserID(conn)
                        c2.execute(
                            "INSERT INTO courses (sid, passwd, courseData, updateTime, userID) VALUES (?, ?, ?, ?, ?)",
                            (
                                username,
                                User.encrypt_password(password),
                                courseData,
                                timeStr,
                                newUserID,
                            ),
                        )
                        status = "success"
                        Crawler.buildHtml(username, newUserID, courseDataJ)
                    else:
                        c2.execute(
                            "UPDATE courses SET passwd = ?, courseData = ?, updateTime = ? WHERE sid = ?",
                            (
                                User.encrypt_password(password),
                                courseData,
                                timeStr,
                                username,
                            ),
                        )
                        status = "success"
                        Crawler.buildHtml(username, userID[0], courseDataJ)
                    logger.info("更新成功 " + username + " 的课表")
                    # print(courseData)
                except Exception as e:
                    logger.exception(e)
                finally:
                    c2.close()
                    conn.commit()
                return status
            else:
                logger.warning(username + "获取课程列表失败")
                c2 = conn.cursor()
                try:
                    cursor = c2.execute(
                        "SELECT userID FROM courses WHERE sid = " + username
                    )
                    userID = cursor.fetchone()
                    if userID is None:
                        newUserID = User.getNewUserID(conn)
                        c2.execute(
                            "INSERT INTO courses (sid, passwd, userID) VALUES (?, ?, ?)",
                            (
                                username,
                                User.encrypt_password(password),
                                newUserID,
                            ),
                        )
                    else:
                        c2.execute(
                            "UPDATE courses SET passwd = ? WHERE sid = ?",
                            (User.encrypt_password(password), username),
                        )
                except Exception as e:
                    logger.exception(e)
                finally:
                    c2.close()
                    conn.commit()
                return "[err]crawl course data error"
        else:
            logger.warning(username + "登录失败")
            return loginRes
    except Exception as e:
        logger.exception(e)
        return "[err]unknown error"


def updateCourseForAllUser():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cursor = c.execute("SELECT count(*) from courses")
    logger.warning("总共有 " + str(cursor.fetchone()[0]) + " 条数据")
    cursor = c.execute("SELECT sid, passwd from courses")
    for row in cursor:
        try:
            username = str(row[0])
            password = User.decrypt_password(str(row[1]))
            result = updateCourse(conn, username, password)
            logger.info(result)
        except Exception as e:
            logger.exception(e)
        time.sleep(random.randint(100, 200) / 10)
    c.close()
    conn.close


def signal_handler(sig, frame):
    global exit_signal
    exit_signal = True
    logger.warning("receive a signal {}".format(sig))
    os.kill(os.getpid(), signal.SIGTERM)


if __name__ == "__main__":
    logger = logging.getLogger("Course")
    logger.setLevel(logging.DEBUG)

    rf_handler = logging.handlers.TimedRotatingFileHandler(
        "./logs/all.log",
        when="midnight",
        interval=1,
        backupCount=7,
        atTime=datetime.time(0, 0, 0, 0),
    )
    rf_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    rf_handler.setLevel(logging.DEBUG)

    f_handler = logging.FileHandler("./logs/error.log")
    f_handler.setLevel(logging.WARNING)
    f_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s - %(filename)s[:%(lineno)d] - %(message)s"
        )
    )

    screen_handler = logging.StreamHandler()
    screen_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    screen_handler.setLevel(logging.DEBUG)

    logger.addHandler(rf_handler)
    logger.addHandler(f_handler)

    if len(sys.argv) >= 2 and sys.argv[1] == "listen":
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        thread = ApiServerThread()
        thread.start()
        # websocket.enableTrace(True)
        ws = websocket.WebSocketApp(
            WS_LISTEN_URL,
            on_message=WsHandler.onWebsocketMessage,
            on_error=WsHandler.onWebsocketError,
            on_close=WsHandler.onWebsocketClose,
        )
        logger.warning("### Websocket started ###")
        ws.run_forever(ping_interval=60, ping_timeout=5)
        while True:
            pass
    elif len(sys.argv) >= 2 and sys.argv[1] == "update":
        logger.addHandler(screen_handler)
        updateCourseForAllUser()
    else:
        print("Usage: python index.py [listen|update] [noproxy|proxy]")
