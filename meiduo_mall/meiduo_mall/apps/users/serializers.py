from rest_framework import serializers
from django_redis import get_redis_connection
import re
from rest_framework_jwt.settings import api_settings
from .models import User


class CreateUserSerialzier(serializers.ModelSerializer):

    # 定义模型外部字段
    password2 = serializers.CharField(label='确认密码', write_only=True)
    sms_code = serializers.CharField(label='短信验证码', write_only=True)
    allow = serializers.CharField(label='同意协议', write_only=True)
    token = serializers.CharField(label='登录状态保持', read_only=True)
    class Meta:
        model = User
        # 所有字段：'id', 'username', 'mobile', 'password', 'password2', 'sms_code', 'allow'
        # 模型内部字段：'id', 'username', 'mobile', 'password'
        # 模型以外字段：'password2', 'sms_code', 'allow'
        # 输入字段(write_only): 'username', 'mobile', 'password', 'password2', 'sms_code', 'allow'
        # 输出字段(read_only): 'id', 'username', 'mobile'
        fields = ['id', 'username', 'mobile', 'password', 'password2', 'sms_code', 'allow', 'token']

        # 给username、password指定额外参数
        extra_kwargs = {
            'username': {
                'min_length': 5,
                'max_length': 20,
                'error_messages': {
                    'min_length': '仅允许5-20个字符的用户名',
                    'max_length': '仅允许5-20个字符的用户名',
                }
            },
            'password': {
                'write_only': True,
                'min_length': 8,
                'max_length': 20,
                'error_messages': {
                    'min_length': '仅允许8-20个字符的密码',
                    'max_length': '仅允许8-20个字符的密码',
                }
            }
        }

    def validate_mobile(self, value):
        """验证手机号"""

        if not re.match(r'^1[3-9]\d{9}$', value):
            raise serializers.ValidationError('手机号格式错误')
        return value

    def validate_allow(self, value):
        """检验用户是否同意"""
        if value != 'true':
            raise serializers.ValidationError('请同意用户协议')
        return value

    def validate(self, data):
        """判断两次密码是否相同"""
        if data['password'] != data['password2']:
            raise serializers.ValidationError('两次密码不一致')

        # 判断短信验证码
        redis_conn = get_redis_connection('verify_codes')
        mobile = data['mobile']
        real_sms_code = redis_conn.get('sms_%s' % mobile)

        if real_sms_code is None:
            raise serializers.ValidationError('无效的短信验证码')

        if data['sms_code'] != real_sms_code.decode():
            raise serializers.ValidationError('短信验证码错误')

        return data

    def create(self, validated_data):
        """
        重写序列化器的create方法：因为有些字段不能默认往User里面存储
        :param validated_data: 经过校验之后的数据
        :return: user ／ # 输出字段(read_only): 'id', 'username', 'mobile'
        """

        # 删除不需要保存的User里的数据
        del validated_data['password2']
        del validated_data['sms_code']
        del validated_data['allow']

        # 自己实现保存数据到User
        user = User.objects.create(**validated_data)

        # 调用django的认证系统加密密码
        user.set_password(validated_data['password'])
        user.save()

        # 必须在注册或者登录之后，响应注册或者登录结果之前，生成jwt_token
        jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER
        jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER
        # 生成载荷：包含了user_id,username,email
        payload = jwt_payload_handler(user)
        # jwt_token
        token = jwt_encode_handler(payload)

        # 将token添加到user : python是面向对象的高级动态编程语言
        user.token = token

        # 响应数据:只会响应read_only字段,
        # 输出字段(read_only)：'id', 'username', 'mobile', 'token'
        return user