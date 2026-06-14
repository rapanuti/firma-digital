"""
Django settings para el proyecto firma_digital.

La configuración se lee de variables de entorno (.env) mediante django-environ,
de modo que el mismo código sirve para desarrollo y producción cambiando solo el
archivo .env. Ver .env.example para la lista de variables.
"""

from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Rutas base y carga de .env
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_SECURE_SSL=(bool, False),
    MAX_PDF_SIZE_MB=(int, 20),
    MAX_IMAGE_SIZE_MB=(int, 5),
)

# Lee el archivo .env si existe (en producción las variables pueden venir del entorno).
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Seguridad básica
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# URL pública base para construir los enlaces de verificación del QR.
# En producción debe ser el dominio real, p.ej. https://midominio.com
VERIFICATION_BASE_URL = env("VERIFICATION_BASE_URL", default="http://localhost:8000")

# Si se muestra el nombre del documento en la página pública de verificación.
# Poner en False si el título pudiera comprometer la privacidad.
VERIFICATION_SHOW_DOCUMENT_TITLE = env.bool("VERIFICATION_SHOW_DOCUMENT_TITLE", default=True)

# ---------------------------------------------------------------------------
# Aplicaciones
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps del proyecto
    "accounts",
    "documents",
    "signing",
    "verification",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # sirve estáticos en producción
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "firma_digital.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "firma_digital.wsgi.application"

# ---------------------------------------------------------------------------
# Base de datos (PostgreSQL vía DATABASE_URL)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://oanzola@localhost:5432/firma_digital",
    ),
}

# ---------------------------------------------------------------------------
# Modelo de usuario custom (debe fijarse antes de la primera migración)
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# ---------------------------------------------------------------------------
# Validación de contraseñas
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internacionalización (español / Venezuela)
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Caracas"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Archivos estáticos y media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # En dev: storage simple (no requiere collectstatic, {% static %} funciona).
        # En prod: comprimido + manifest de whitenoise (tras collectstatic).
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Límites de subida (seguridad: evitar archivos enormes)
# ---------------------------------------------------------------------------
MAX_PDF_SIZE_MB = env("MAX_PDF_SIZE_MB")
MAX_IMAGE_SIZE_MB = env("MAX_IMAGE_SIZE_MB")
# El cuerpo de la petición no-archivo se limita aparte; los archivos van a disco.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB para campos no-archivo
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # por encima de esto -> archivo temporal

# ---------------------------------------------------------------------------
# Endurecimiento para producción (se activa cuando DJANGO_SECURE_SSL=True)
# ---------------------------------------------------------------------------
if env("DJANGO_SECURE_SSL"):
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = env(
        "DJANGO_CSRF_TRUSTED_ORIGINS", default=[VERIFICATION_BASE_URL]
    )

# ---------------------------------------------------------------------------
# Logging básico a consola (auditoría de aplicación se guarda en BD aparte)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
