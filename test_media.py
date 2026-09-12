import os, sys
print("sys.path:", sys.path[:5])
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.production')
import django
try:
    django.setup()
    print("django setup ok")
except Exception as e:
    print("django setup err:", repr(e))
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import UploadedFile
b=Image.open('media/products/product_big.png').convert('RGB')
buf=BytesIO(); b.save(buf, format='JPEG', quality=85)
f=UploadedFile(file=buf, name='test.jpg', size=buf.tell())
print('size bytes:', f.size, 'name:', f.name)
