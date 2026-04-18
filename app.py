# app.py
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, date
import time

# ============ 初始化Flask应用 ============
app = Flask(__name__)

# ============ 数据库配置 ============
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'

# 初始化数据库
db = SQLAlchemy(app)


# ============ 升级：用户表（增加房源信息）============
# 解释：每个联系人现在都可以关联一个房源信息
class User(db.Model):
    """
    用户表 - 存储所有联系人信息
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    avatar = db.Column(db.String(10), default="👤")
    role = db.Column(db.String(20), default="landlord")
    # 👇 新增：房源信息字段
    house_title = db.Column(db.String(200), default="朝阳区三居室")
    house_price = db.Column(db.String(50), default="5000元/月")
    house_area = db.Column(db.String(50), default="80㎡")
    house_location = db.Column(db.String(100), default="朝阳区")

    last_message = db.Column(db.String(100), default="")
    last_message_time = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'avatar': self.avatar,
            'role': self.role,
            'house_title': self.house_title,
            'house_price': self.house_price,
            'house_area': self.house_area,
            'house_location': self.house_location,
            'last_message': self.last_message,
            'last_message_time': self.last_message_time.strftime('%H:%M') if self.last_message_time else ''
        }


# ============ 消息表（保持不变）============
class Message(db.Model):
    """
    消息表 - 存储所有聊天消息
    """
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sender_id = db.Column(db.Integer, nullable=False)
    recipient_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_auto_reply = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'recipient_id': self.recipient_id,
            'content': self.content,
            'is_auto_reply': self.is_auto_reply,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }


# ============ 预约数据库模型（保持不变）============
class Booking(db.Model):
    """预约记录表"""
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(50), default="张三")
    house_title = db.Column(db.String(200), default="阳光两居室")
    visit_date = db.Column(db.Date, nullable=False)
    visit_time = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


# ============ 新增：自动回复关键词字典============
# 解释：根据用户消息中的关键词，自动回复对应的内容
AUTO_REPLY_KEYWORDS = {
    '租金': '这套房子的租金是{price}，包含物业费，押一付三。如果长租可以优惠哦~',
    '价格': '租金是{price}，性价比很高！周边配套齐全。',
    '多少钱': '房租是{price}，欢迎来看房详谈~',
    '面积': '这套房子面积是{area}，三室一厅，空间很宽敞！',
    '大小': '房子{area}，户型方正，采光好。',
    '位置': '房子在{location}，交通便利，地铁5分钟。',
    '地址': '具体地址是{location}，附近有商场和学校。',
    '哪里': '房源位置：{location}，周边生活设施完善。',
    '看房': '欢迎随时来看房！我的空闲时间是工作日晚上和周末全天。您方便什么时候呢？',
    '预约': '好的！您可以点击右上角"预约看房"按钮选择时间，或者直接告诉我您方便的时间~',
    '家具': '房子配有全套家具：床、沙发、冰箱、洗衣机、空调等，拎包入住！',
    '家电': '家电齐全：冰箱、洗衣机、空调、热水器、电视，都是近两年新买的。',
    '宠物': '可以养宠物，但需要保持房屋清洁哦。',
    '合租': '这套房子适合整租，也可以合租，具体可以面谈。',
    '水电': '水电燃气费用按实际使用量缴纳，一般每月200元左右。',
    '物业费': '物业费包含在租金里，不需要另外交。',
    '押金': '押金是一个月租金，退租时没有损坏会全额退还。',
    '合同': '签订正规租赁合同，保障双方权益。',
    '你好': '您好！很高兴为您服务，请问有什么可以帮您的吗？',
    '在吗': '在的！有什么问题尽管问我~',
    '您好': '您好呀！欢迎咨询~',
}

# 默认自动回复（当没有匹配到关键词时）
DEFAULT_AUTO_REPLY = '您好，我暂时不在，稍后会尽快回复您！您也可以点击右上角预约看房哦~'


# ============ 新增：智能自动回复函数 ============
def generate_auto_reply(user_message, contact):
    """
    解释：根据用户消息内容，生成智能自动回复
    user_message: 用户发送的消息内容
    contact: 联系人对象（包含房源信息）
    """
    # 把用户消息转换成小写，方便匹配
    message_lower = user_message.lower()

    # 遍历所有关键词，看用户消息里有没有
    for keyword, reply_template in AUTO_REPLY_KEYWORDS.items():
        if keyword in message_lower:
            # 找到匹配的关键词，替换模板中的房源信息
            reply = reply_template.format(
                price=contact.house_price,
                area=contact.house_area,
                location=contact.house_location
            )
            return reply

    # 如果没有匹配到任何关键词，返回默认回复
    return DEFAULT_AUTO_REPLY


# ============ 聊天主页 ============
@app.route('/chat')
def chat_home():
    """
    聊天主页 - 显示左侧联系人列表
    """
    contacts = User.query.filter(User.id != 1).order_by(User.last_message_time.desc()).all()

    return render_template('chat.html',
                           contacts=contacts,
                           current_contact=None,
                           messages=[])


# ============ 与特定联系人的对话页面 ============
@app.route('/chat/<int:contact_id>')
def chat_with_contact(contact_id):
    """
    与指定联系人的聊天页面
    """
    contacts = User.query.filter(User.id != 1).order_by(User.last_message_time.desc()).all()
    current_contact = User.query.get(contact_id)

    if not current_contact:
        return redirect(url_for('chat_home'))

    messages = Message.query.filter(
        ((Message.sender_id == 1) & (Message.recipient_id == contact_id)) |
        ((Message.sender_id == contact_id) & (Message.recipient_id == 1))
    ).order_by(Message.timestamp.asc()).all()

    messages_dict = [msg.to_dict() for msg in messages]

    return render_template('chat.html',
                           contacts=contacts,
                           current_contact=current_contact,
                           messages=messages_dict)


# ============ 获取历史消息API ============
@app.route('/api/messages/<int:contact_id>', methods=['GET'])
def get_messages(contact_id):
    """
    获取与指定联系人的聊天记录
    """
    messages = Message.query.filter(
        ((Message.sender_id == 1) & (Message.recipient_id == contact_id)) |
        ((Message.sender_id == contact_id) & (Message.recipient_id == 1))
    ).order_by(Message.timestamp.asc()).all()

    return jsonify([msg.to_dict() for msg in messages])


# ============ 升级：发送消息API（增加自动回复）============
@app.route('/api/send_message', methods=['POST'])
def send_message():
    """
    发送消息并保存到数据库
    如果是用户发的消息，会触发对方的自动回复
    """
    data = request.get_json()
    sender_id = data.get('sender_id')
    recipient_id = data.get('recipient_id')
    content = data.get('content')

    # 1. 保存用户发送的消息
    new_message = Message(
        sender_id=sender_id,
        recipient_id=recipient_id,
        content=content,
        is_auto_reply=False
    )
    db.session.add(new_message)
    # 2. 更新对方的"最后一条消息"
    contact = User.query.get(recipient_id)
    if contact:
        contact.last_message = content[:30]
        contact.last_message_time = datetime.now()

    db.session.commit()

    # 3.👇 新增：如果是用户（ID=1）发的消息，生成自动回复
    auto_reply_message = None
    if sender_id == 1 and contact:
        # 等待0.5秒，模拟对方正在输入
        time.sleep(0.5)

        # 生成自动回复内容
        auto_reply_content = generate_auto_reply(content, contact)

        # 保存自动回复消息
        auto_reply_message = Message(
            sender_id=recipient_id,  # 对方发送
            recipient_id=1,  # 发给你
            content=auto_reply_content,
            is_auto_reply=True  # 标记为自动回复
        )
        db.session.add(auto_reply_message)
        # 更新对方的最后消息
        contact.last_message = auto_reply_content[:30]
        contact.last_message_time = datetime.now()
        db.session.commit()

    # 4. 返回结果
    result = {
        'success': True,
        'message': new_message.to_dict()
    }

    # 如果有自动回复，一并返回
    if auto_reply_message:
        result['auto_reply'] = auto_reply_message.to_dict()

    return jsonify(result)


# ========== 预约功能：显示时间表和预约列表 ==========
@app.route('/booking')
def booking():
    """显示可预约时间和已有预约"""

    # 1. 生成未来7天的日期选项
    available_dates = []
    for i in range(7):
        day = date.today() + timedelta(days=i)
        available_dates.append({
            'date': day.strftime('%Y-%m-%d'),  # 格式：2024-01-15
            'weekday': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][day.weekday()]
        })

    # 2. 生成时间段（9:00-18:00，每小时一次）
    available_times = [f"{h:02d}:00" for h in range(9, 19)]

    # 3. 获取所有已预约的记录（按日期倒序）
    my_bookings = Booking.query.order_by(Booking.visit_date.desc()).all()

    # 4. 获取今天已被预约的时间段（用于标记"已约满"）
    today = date.today()
    booked_times_today = [b.visit_time for b in Booking.query.filter_by(visit_date=today).all()]

    return render_template('booking.html', dates=available_dates,
                           times=available_times,
                           bookings=my_bookings,
                           booked_times=booked_times_today,
                           today=today)


# ========== 提交预约 ==========
@app.route('/make_booking', methods=['POST'])
def make_booking():
    """用户点击"预约"按钮后执行"""

    # 1. 获取表单数据
    visit_date_str = request.form.get('date')
    visit_time = request.form.get('time')
    house_title = request.form.get('house_title', '阳光两居室')  # 获取房源名称

    # 2. 转换日期格式
    visit_date = datetime.strptime(visit_date_str, '%Y-%m-%d').date()

    # 3. 检查该时间是否已被预约
    existing = Booking.query.filter_by(visit_date=visit_date, visit_time=visit_time).first()
    if existing:
        flash('这个时间已经被预约了，请选别的时间', 'warning')
        return redirect(url_for('booking'))

    # 4. 创建新预约
    new_booking = Booking(
        visit_date=visit_date,
        visit_time=visit_time,
        house_title=house_title
    )
    db.session.add(new_booking)
    db.session.commit()

    # 5. 渲染成功页面（传递预约ID，用于"返回修改"）
    return render_template('booking_success.html',
                           date=visit_date_str,
                           time=visit_time,
                           house_title=house_title)


# ========== 取消预约 ==========
@app.route('/cancel_booking/<int:booking_id>')
def cancel_booking(booking_id):
    """取消某个预约"""

    # 1. 获取来源页面（从URL参数获取，默认是booking）
    source = request.args.get('source', 'booking')  # 👈 新增：获取来源

    # 2. 查找预约记录
    booking = Booking.query.get(booking_id)

    if not booking:
        flash('预约不存在', 'danger')
        # 根据来源返回不同页面
        if source == 'dashboard':
            return redirect(url_for('dashboard'))
        return redirect(url_for('booking'))

    # 3. 保存信息用于显示
    booking_date = str(booking.visit_date)
    booking_time = booking.visit_time
    house_title = booking.house_title

    # 4. 删除预约
    db.session.delete(booking)
    db.session.commit()

    # 5. 渲染取消成功页面，传递来源信息
    return render_template('cancel_success.html', date=booking_date,
                           time=booking_time,
                           house_title=house_title,
                           source=source)  # 👈 新增：传递来源


# ========== 个人预约日程管理（汇总所有房源）==========
@app.route('/dashboard')
def dashboard():
    """个人主页：查看所有房源的预约日程"""

    # 获取所有预约，按日期降序排列
    all_bookings = Booking.query.order_by(Booking.visit_date.desc()).all()

    # 获取今天的日期（用于判断是否过期）
    today = date.today()

    return render_template('my_dashboard.html', bookings=all_bookings,
                           today=today)


# ============ 数据库初始化（更新测试数据）============
def init_db():
    """
    创建数据库表并添加测试数据
    """
    with app.app_context():
        db.create_all()

        if User.query.count() == 0:
            # 创建你自己（ID=1）
            me = User(id=1, name="我", avatar="👤", role="tenant")

            # 👇 创建更自然的联系人网名
            contact1 = User(
                name="陈小姐",
                avatar="陈",
                role="landlord",
                house_title="太和精装三居室",
                house_price="9000元/月",
                house_area="60㎡",
                house_location="地铁太和站附近",
                last_message="房子家具家电齐全哦",
                last_message_time=datetime.now()
            )

            contact2 = User(
                name="Sunny",
                avatar="☀️",
                role="landlord",
                house_title="大埔墟两居室",
                house_price="8500元/月",
                house_area="55㎡",
                house_location="离港中文大学很近",
                last_message="欢迎随时来看房",
                last_message_time=datetime.now() - timedelta(hours=2)
            )

            contact3 = User(
                name="张先生",
                avatar="张",
                role="landlord",
                house_title="罗湖口岸精装两居室",
                house_price="7000元/月",
                house_area="80㎡",
                house_location="罗湖区",
                last_message="这套房子性价比超高",
                last_message_time=datetime.now() - timedelta(hours=5)
            )

            db.session.add_all([me, contact1, contact2, contact3])
            db.session.commit()
            print("✅ 已添加测试联系人！")

        print("✅ 数据库初始化成功！")


# ============ 程序入口 ============
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)