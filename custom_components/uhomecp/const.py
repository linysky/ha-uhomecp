"""Constants for U管家门禁 integration."""

DOMAIN = "uhomecp"

# API endpoints
BASE_URL = "https://www.uhomecp.com"
LOGIN_URL = "/authc-restapi/v1/user/auth/login"
CAPTCHA_URL = "/authc-restapi/v1/auth/code/getImgCode"
DOOR_LIST_URL = "/door-restapi/v1/userapp/doorList"
OPEN_DOOR_URL = "/uhomecp-app/v1/userapp/opendoor/submit.json"

# RSA public key (from sg-rsa.js)
RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC03KMpYBkJ51nCrWUsMr1E3T5/q
8ETu/UbeJnbyjYD4u3F/4iEECLbUxe9k49gQcb4rR2zciI0Oy8R3x1Irndjc81f9w9
g2fTqNnsM00siVsqh6VGEV9XBkWOUoyg601WNbR3HiIa3GyLvo79oND0mdFBP0QqQc
2h7IMqaR71hEwIDAQAB
-----END PUBLIC KEY-----"""

# Default headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 "
    "KHTML, like Gecko) Version/4.0 Chrome/90.0.4430.91 Mobile Safari/537.36",
    "Referer": f"{BASE_URL}/h5/wechat-platform-h5/",
    "Origin": BASE_URL,
}

# Config flow
CONF_PHONE = "phone"
CONF_PASSWORD = "password"

# Update interval (seconds)
UPDATE_INTERVAL = 300  # 5 minutes
