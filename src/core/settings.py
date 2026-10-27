# SECURITY WARNING: keep the secret key used in production secret!
# You should change this key before you go live!
SITE_ID = 1
SECRET_KEY = "uxprsdhk^gzd-r=_287byolxn)$k6tsd8_cepl^s^tms2w1qrv"

# This is the default redirect if no other sites are found.
#DEFAULT_HOST = "https://www.example.org"
#DEFAULT_HOST = "iranictech.ir"
DEFAULT_HOST = "https://iranictech.ir"
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
LOGIN_REDIRECT_URL = "/user/profile/"

# CATCHA_TYPE should be either 'simple_math', 'recaptcha' or 'hcaptcha' to enable captcha
# fields, otherwise disabled
CAPTCHA_TYPE = "recaptcha"

# If using recaptcha complete the following
RECAPTCHA_PRIVATE_KEY = "6Lcyz08tAAAAAGF3G8d3tPHnWfUAjaGh5en03DoS"
RECAPTCHA_PUBLIC_KEY = "6Lcyz08tAAAAAJwdUVPe45hl0j58VEAEkwrFPw9X"

# If using hcaptcha complete the following:
HCAPTCHA_SITEKEY = ""
HCAPTCHA_SECRET = ""

# ORCID Settings
ENABLE_ORCID = True
ORCID_API_URL = ""  # Not needed any more. Requests are delegated to python-orcid.
ORCID_URL = "https://orcid.org/oauth/authorize"
ORCID_TOKEN_URL = "https://orcid.org/oauth/token"
ORCID_TOKEN_URL = "https://pub.orcid.org/oauth/token"
ORCID_CLIENT_SECRET = "116c85e7-d3e6-4b9e-b3b9-21364618e8bb"
ORCID_CLIENT_ID = "APP-9PQY9J127G4LOQYJ"

# Default Langague
LANGUAGE_CODE = "en"

#URL_CONFIG = "path"  # path or domain
URL_CONFIG = "domain"
DATABASES = {
    "default": {
        # Example ENGINEs:
        #   sqlite:     'django.db.backends.sqlite
        #   mysql:      'django.db.backends.mysql
        #   postgres:   'django.db.backends.postgresql
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "janewaydb",
        "USER": "janewayuser",
        "PASSWORD": "ramsar227",
        "HOST": "localhost",
        "PORT": "5432",
        
    }
}


# OIDC Settings
ENABLE_OIDC = False
OIDC_SERVICE_NAME = "OIDC Service Name"
OIDC_RP_CLIENT_ID = ""
OIDC_RP_CLIENT_SECRET = ""
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_OP_AUTHORIZATION_ENDPOINT = ""
OIDC_OP_TOKEN_ENDPOINT = ""
OIDC_OP_USER_ENDPOINT = ""
OIDC_OP_JWKS_ENDPOINT = ""


ENABLE_FULL_TEXT_SEARCH = False  # Read the docs before enabling full text

# Model used for indexing full text files
CORE_FILETEXT_MODEL = "core.FileText"  # Use "core.PGFileText" for Postgres

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT =  False
USE_X_FORWARDED_HOST = True

# Production Settings
#DEBUG = False
DEBUG = False
#ALLOWED_HOSTS = ['65.109.220.223', 'localhost', '127.0.0.1']
CSRF_TRUSTED_ORIGINS = ['https://iranictech.ir', 'https://www.iranictech.ir']
ALLOWED_HOSTS = [
    "iranictech.ir",
    "www.iranictech.ir",
    "65.109.220.223",
]
