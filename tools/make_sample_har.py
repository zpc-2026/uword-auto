"""造一份示例 HAR（模拟小程序抓包），用来验证 har2config.py 的识别效果。"""
import json
import pathlib

HOST = "https://api.uword-demo.cn"


def entry(method, path, body=None):
    return {
        "_resourceType": "xhr",
        "request": {
            "method": method,
            "url": HOST + path,
            "headers": [
                {"name": "User-Agent", "value": "MicroMessenger/8.0.49 miniProgram"},
                {"name": "Referer", "value": "https://servicewechat.com/wx1234567890/12/page-frame.html"},
                {"name": "token", "value": "eyJhbGciOiJIUzI1NiJ9.SAMPLE.SIGN"},
                {"name": "Cookie", "value": "SESSION=sample-cookie"},
                {"name": "X-Device-Id", "value": "device-sample-01"},
            ],
        },
        "response": {"content": {"mimeType": "application/json", "text": "{}"}},
    }


ENTRIES = [
    entry("GET", "/api/v1/wordbook/list"),
    entry("GET", "/api/v1/word/list?bookId=B001&page=1&size=30"),
    entry("POST", "/api/v1/study/start"),
    entry("POST", "/api/v1/study/word"),
    entry("POST", "/api/v1/study/heartbeat"),
    entry("GET", "/api/v1/quiz/list?bookId=B001"),
    entry("POST", "/api/v1/quiz/submit"),
    entry("GET", "/api/v1/review/list?bookId=B001"),
    entry("GET", "/static/app.js"),
]

har = {"log": {"version": "1.2", "creator": {"name": "sample"}, "entries": ENTRIES}}
pathlib.Path("sample.har").write_text(json.dumps(har, ensure_ascii=False, indent=2), encoding="utf-8")
print("sample.har written")
