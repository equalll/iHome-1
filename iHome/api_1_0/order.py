# -*- coding: utf-8 -*-
from datetime import datetime
from flask import request, jsonify, current_app, g

from iHome import db
from iHome.models import House, Order
from iHome.response_code import RET
from . import api
from iHome.utils.commons import login_required


@api.route('/orders/<int:order_id>/comment', methods=['PUT'])
@login_required
def save_order_comment(order_id):
    """
    保存评价信息
    # 1.接收评论参数并进行校验
    # 2.根据订单id查询订单信息
    # 3.更改订单状态，保存评价信息
    # 4.提交数据库
    # 5.返回应答
    :return: 
    """
    # 1.接收评论参数并进行校验
    req_dict = request.json
    comment = req_dict.get('comment')
    if not comment:
        return jsonify(errno=RET.PARAMERR, errmsg='缺少参数')

    # 2.根据订单id查询订单信息
    try:
        order = Order.query.filter(Order.id == order_id,
                               Order.status == 'WAIT_COMMENT',
                               Order.user_id == g.user_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询订单失败')

    if not order:
        return jsonify(errno=RET.NODATA, errmsg='订单不存在')

    # 3.更改订单状态，保存评价信息
    order.status = 'COMPLETE'
    order.comment = comment
    # 4.提交数据库
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='保存订单信息失败')
    # 5.返回应答
    return jsonify(errno=RET.OK, errmsg='OK')

@api.route('/orders/<int:order_id>/status', methods=['PUT'])
@login_required
def update_order_status(order_id):
    """
    # /orders/<int:order_id>/status?action=accept|reject
    进行接单或拒单
    1.接收数据action进行校验，action=accept（接单），action=reject（拒单）
    2.根据订单id查询订单信息
    3.根基action设置订单状态
    4.更新数据库
    5.返回应答
    :param order_id: 
    :return: 
    """
    # 1.接收数据action进行校验，action = accept（接单），action = reject（拒单）
    action = request.args.get('action')
    if action not in ['accept', 'reject']:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 2.根据订单id查询订单信息
    try:
        order = Order.query.filter(Order.id == order_id,
                                   Order.status == 'WAIT_ACCEPT').first()
        # 获取房东id
        landlord_id = order.house.user_id
        # 判断当前登录的用户是否是房东
        if landlord_id != g.user_id:
            return jsonify(errno=RET.DATAERR, errmsg='不是房东')
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询订单失败')

    if not order:
        return jsonify(errno=RET.DATAERR, errmsg='订单不存在')
    # 3.根基action设置订单状态
    if action == 'accept':
        order.status = 'WAIT_COMMENT' # 待评价
    else:
        req_dict = request.json
        reason = req_dict.get('reason')
        if not reason:
            return jsonify(errno=RET.PARAMERR, errmsg='缺少参数')
        order.comment = reason
        order.status = 'REJECTED'
    # 4.更新数据库
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='保存订单信息失败')

    # 5.返回应答
    return jsonify(errno=RET.OK, errmsg='OK')


@api.route('/orders')
@login_required
def get_order_list():
    """
    获取用户的订单信息:
    1. 根据用户的id查询出用户的所有订单的信息，按照订单的创建时间进行排序
    2. 组织数据，返回应答
    """
    # role=lodger, 代表以房客的身份查询预订其他人房屋的订单
    # role=landlord, 代表以房东的身份查询其他人预订自己房屋的订单
    role = request.args.get('role')
    if role not in ['lodger', 'landlord']:
        return jsonify(errno=RET.PARAMERR, errmsg='数据错误')

    user_id = g.user_id

    try:
        if role == 'lodger':
            orders = Order.query.filter(Order.user_id == user_id).order_by(Order.create_time.desc()).all()
        else:
            houses = House.query.filter(House.user_id == user_id).all()
            houses_li_id = [house.id for house in houses]
            orders = Order.query.filter(Order.house_id.in_(houses_li_id)).order_by(Order.create_time.desc()).all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询订单信息失败')

    order_dict_li = []
    for order in orders:
        order_dict_li.append(order.to_dict())

    return jsonify(errno=RET.OK, errmsg='OK', data=order_dict_li)


@api.route('/orders', methods=['POST'])
@login_required
def save_order_info():
    """
    保存房屋预订订单的信息:
    1. 接收参数(房屋id, 起始时间，结束时间) 并进行参数校验
    2. 根据房屋id查询房屋信息（如果查不到，说明房屋信息不存在)
    3. 根据入住起始时间和结束时间查询订单是否有冲突
    4. 创建Order对象并保存订单信息
    5. 把订单信息添加进数据库
    6. 返回应答，订单创建成功
    """
    # 1. 接收参数(房屋id, 起始时间，结束时间) 并进行参数校验
    req_dict = request.json
    house_id = req_dict.get('house_id')
    start_date = req_dict.get('start_date')
    end_date = req_dict.get('end_date')

    if not all([house_id, start_date, end_date]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数不完整')

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

        assert start_date<end_date, Exception('起始时间大于结束时间')
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 2.根据房屋id查询房屋信息（如果查不到，说明房屋信息不存在)
    try:
        house = House.query.get(house_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询房屋信息失败')

    if not house:
        return jsonify(errno=RET.NODATA, errmsg='房屋不存在')

    # 3.根据入住起始时间和结束时间查询订单是否有冲突
    try:
        conflict_orders_count = Order.query.filter(end_date>Order.begin_date,
                                                   start_date<Order.end_date,
                                                   Order.house_id == house_id).count()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询冲突订单失败')

    if conflict_orders_count>0:
        return jsonify(errno=RET.DATAERR, errmsg='房屋已被预订')

    # 4.创建Order对象并保存订单信息
    days = (end_date-start_date).days
    order = Order()
    order.user_id = g.user_id
    order.house_id = house_id
    order.begin_date = start_date
    order.end_date = end_date
    order.house_price = house.price
    order.amount = house.price * days
    order.days = days

    house.order_count += 1

    # 5.把订单信息添加进数据库
    try:
        db.session.add(order)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='保存订单信息失败')

    # 6.返回应答，订单创建成功
    return jsonify(errno=RET.OK, errmsg='OK')