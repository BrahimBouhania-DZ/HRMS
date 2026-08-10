# HRMS — إعداد Gunicorn (إنتاج LAN)
# الاستعمال: gunicorn -c deploy/gunicorn.conf.py config.wsgi:application
#   4 عمليات — كافية لفرع LAN؛ عدّل العمال حسب حجم الفريق.

import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
timeout = 120
graceful_timeout = 30

accesslog = "-"
errorlog = "-"
