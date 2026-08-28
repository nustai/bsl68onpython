"""Small TitanEngine message constants retained from the C# project."""


class TitanLoginMessage:
    message_type = 10101


class TitanLoginFailedMessage:
    message_type = 20103


class TitanDisconnectedMessage:
    message_type = 25892


class PepperPerMessageEncrypter:
    @staticmethod
    def self_test() -> int:
        return 1

    @staticmethod
    def get_encryption_overhead() -> int:
        return 0
