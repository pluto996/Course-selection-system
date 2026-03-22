import os
from PIL import Image, UnidentifiedImageError

AVATAR_DIR = os.path.join('static', 'avatars')
MAX_SIZE = 2 * 1024 * 1024  # 2MB
ALLOWED_MIMES = {'image/jpeg', 'image/png'}
OUTPUT_SIZE = (200, 200)


class AvatarValidationError(Exception):
    pass


def save_avatar(file, user_id: int) -> str:
    """
    验证并保存头像文件。
    :param file: werkzeug FileStorage 对象
    :param user_id: 用户 ID
    :return: 相对路径（如 'static/avatars/1.jpg'）
    :raises AvatarValidationError: 验证失败时
    """
    # 验证 MIME 类型
    mime = file.mimetype or ''
    if mime not in ALLOWED_MIMES:
        # 尝试从文件名推断
        fname = (file.filename or '').lower()
        if not (fname.endswith('.jpg') or fname.endswith('.jpeg') or fname.endswith('.png')):
            raise AvatarValidationError('文件格式不支持，请上传 JPG 或 PNG 图片')

    # 读取内容验证大小
    content = file.read()
    if len(content) > MAX_SIZE:
        raise AvatarValidationError('文件大小超过 2MB 限制')

    # 验证图片有效性
    import io
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        img = Image.open(io.BytesIO(content))  # verify 后需重新打开
    except (UnidentifiedImageError, Exception):
        raise AvatarValidationError('文件格式或大小不符合要求')

    # 转为 RGB（处理 PNG 透明通道）
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')

    # 裁剪为正方形（取短边）
    w, h = img.size
    min_side = min(w, h)
    left = (w - min_side) // 2
    top = (h - min_side) // 2
    img = img.crop((left, top, left + min_side, top + min_side))

    # 缩放至 200×200
    img = img.resize(OUTPUT_SIZE, Image.LANCZOS)

    # 确保目录存在
    os.makedirs(AVATAR_DIR, exist_ok=True)

    # 保存
    save_path = os.path.join(AVATAR_DIR, f'{user_id}.jpg')
    img.save(save_path, 'JPEG', quality=90)

    return f'avatars/{user_id}.jpg'
