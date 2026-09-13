import io
import uuid
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException
from sqlalchemy import select
from backend.config import settings
from backend.models import File, MenuItem, Review

MAX_BYTES = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20000000

def upload(db, user, upload, purpose, entity_id):
    allowed = {'customer': {'profile','review'}, 'restaurant': {'profile','menu','fssai','gst','license','cover','logo','gallery'}, 'driver': {'profile','license','rc','id_proof'}}
    if purpose not in allowed[user.role]:
        raise HTTPException(400, 'Invalid document purpose')
    if purpose in {'menu','review'}:
        model = MenuItem if purpose == 'menu' else Review
        row = db.get(model, entity_id) if entity_id else None
        if not row or getattr(row, 'restaurant_id' if purpose == 'menu' else 'customer_id') != user.id:
            raise HTTPException(404, 'Upload target not found')
    if purpose in {'cover','logo','gallery'} and entity_id != user.id:
        raise HTTPException(404, 'Upload target not found')
    raw = upload.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, 'Maximum file size is 5 MB')
    try:
        with Image.open(io.BytesIO(raw)) as picture:
            picture.load()
            output = io.BytesIO()
            picture.convert('RGB').save(output, format='JPEG', quality=88)
            raw = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, 'Upload a valid JPEG, PNG or WebP image')
    directory = Path(settings.file_root) / (user.role + 's') / str(user.id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    path = directory / (uuid.uuid4().hex + '.jpg')
    try:
        with path.open('xb') as stream:
            stream.write(raw)
        path.chmod(0o640)
        if purpose == 'menu':
            thumbnail_path(path)
        row = File(user_id=user.id, purpose=purpose, entity_id=entity_id, path=str(path), mime='image/jpeg')
        db.add(row)
        db.flush()
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        path.with_name(path.stem + '.thumb320.jpg').unlink(missing_ok=True)
        raise
    return {'id':row.id, 'purpose':purpose}

def listing(db, user):
    return [{'id':r.id, 'purpose':r.purpose, 'entity_id':r.entity_id} for r in db.scalars(select(File).where(File.user_id == user.id))]

def download(db, user, file_id):
    row = db.get(File, file_id)
    if not row or (row.user_id != user.id and row.purpose not in {'menu','review','cover','logo','gallery'}):
        raise HTTPException(404, 'File not found')
    path = Path(row.path).resolve()
    if not path.is_relative_to(Path(settings.file_root).resolve()) or not path.is_file():
        raise HTTPException(404, 'File not found')
    return path

def thumbnail_path(path):
    import os
    import tempfile
    from PIL import ImageOps
    target = path.with_name(path.stem + '.thumb320.jpg')
    if target.is_file():
        return target
    temporary = None
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((320, 320), Image.Resampling.LANCZOS)
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                image.convert('RGB').save(stream, format='JPEG', quality=80, optimize=True)
        temporary.chmod(0o640)
        os.replace(temporary, target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return target

def thumbnail(db, user, file_id):
    return thumbnail_path(download(db, user, file_id))
