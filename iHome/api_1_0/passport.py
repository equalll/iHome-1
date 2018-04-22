# -*- coding: utf-8 -*-
import re
from flask import request, jsonify, current_app, session

from iHome import redis_store, db
from iHome.models import User
from iHome.response_code import RET
from . import api


@api.route('/session',methods=['POST'])
def login():
    """
    登录
    1、获取参数，并校验完整性
    2、根据手机号验证用户信息
    3、验证密码
    4、session记录用户登录状态
    5、返回应答
    :return: 
    """
    # 1、获取参数，并校验完整性
    req_dict = request.json
    mobile = req_dict.get('mobile')
    password = req_dict.get('password')

    if not all([mobile, password]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数不完整')

    if not re.match(r'^1[3456789]\d{9}$', mobile):
        return jsonify(errno=RET.PARAMERR, errmsg='手机号格式不正确')

    # 2、根据手机号验证用户信息
    try:
        user = User.query.filter(User.mobile == mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询用户信息失败')

    if not user:
        return jsonify(errno=RET.USERERR, errmsg='用户不存在')
    # 3、验证密码
    if not user.check_user_password(password):
        return jsonify(errno=RET.PWDERR, errmsg='登录密码错误')
    # 4、session记录用户登录状态
    session['user_id'] = user.id
    session['user_name'] = user.name
    session['mobile'] = user.mobile

    # 5、返回应答
    return jsonify(errno=RET.OK, errmsg='登录成功')


@api.route('/users', methods=['POST'])
def register():
    """
    注册功能实现
    1. 获取参数（手机号，短信验证码，密码），并校验
    2. redis读取短信验证码，
    3. 对比短信验证码
    4. 创建用户，并保存用户信息
    5. 添加信息到数据库
    6. 返回应答
    :return: 
    """
    # 1. 获取参数（手机号，短信验证码，密码），并校验
    req_dict = request.json
    mobile = req_dict.get('mobile')
    phonecode = req_dict.get('phonecode')
    password = req_dict.get('password')
    print req_dict

    if not all([mobile, phonecode, password]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数不完整')
    # 2. redis读取短信验证码，
    try:
        sms_code = redis_store.get('sms_code:%s' % mobile)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.NODATA, errmsg='查询短信验证码失败')
    # 3. 对比短信验证码
    if sms_code != phonecode:
        return jsonify(errno=RET.DATAERR, errmsg='短信验证码错误')

    # 4. 创建用户，并保存用户信息
    user = User()
    user.mobile = mobile
    user.name = mobile
    # 密码加密
    user.password = password
    # 5. 添加信息到数据库
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errsmg='保存用户信息失败')
    # 6. 返回应答
    return jsonify(errno=RET.OK, errmsg='注册成功')