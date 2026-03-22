from flask import request
from flask_login import current_user

LOGIN = 'LOGIN'
LOGOUT = 'LOGOUT'
USER_CREATE = 'USER_CREATE'
USER_DISABLE = 'USER_DISABLE'
USER_ENABLE = 'USER_ENABLE'
PASSWORD_RESET = 'PASSWORD_RESET'
PASSWORD_CHANGE = 'PASSWORD_CHANGE'
XML_IMPORT = 'XML_IMPORT'
SCHEDULE_GENERATE = 'SCHEDULE_GENERATE'
NOTIFICATION_PUBLISH = 'NOTIFICATION_PUBLISH'
APPLICATION_REVIEW = 'APPLICATION_REVIEW'

ACTION_LABELS = {
    LOGIN: '用户登录',
    LOGOUT: '用户登出',
    USER_CREATE: '创建用户',
    USER_DISABLE: '停用用户',
    USER_ENABLE: '启用用户',
    PASSWORD_RESET: '重置密码',
    PASSWORD_CHANGE: '修改密码',
    XML_IMPORT: 'XML数据导入',
    SCHEDULE_GENERATE: '排课生成',
    NOTIFICATION_PUBLISH: '发布通知',
    APPLICATION_REVIEW: '审批选课申请',
}


def log_action(action_type, result='success', detail='', operator=None, user_id=None):
    from models import db, AuditLog
    try:
        op = operator
        uid = user_id
        if op is None:
            if current_user and current_user.is_authenticated:
                op = current_user.username
                if uid is None:
                    uid = current_user.id
            else:
                op = 'anonymous'
        ip = request.remote_addr if request else '0.0.0.0'
        db.session.add(AuditLog(
            user_id=uid,
            operator=op,
            action_type=action_type,
            ip_address=ip,
            result=result,
            detail=detail
        ))
        db.session.commit()
    except Exception as e:
        print(f'[AuditLog Error] {e}')
