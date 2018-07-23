import time
import json
import requests
import urllib
import http.client
import hmac
import hashlib

# Если нет нужных пакетов - читаем тут: https://bablofil.ru/python-indicators/
import numpy
import talib

from datetime import datetime
import numpy as np
#
import sqlite3

# ключи API, которые предоставила exmo
API_KEY = ''
# обратите внимание, что добавлена 'b' перед строкой
API_SECRET = b''

# Список пар, на которые торгуем
MARKETS = [
    # 'BCH_USD', 'HBZ_USD', 'BTG_USD', 'BTC_USD',
    # 'ZEC_USD', 'DASH_USD', 'XRP_USD', 'ETH_USD',
    # 'EOS_USD', 'LTC_USD',
    'ETH_RUB'
]

QUOTE_CURRENCY = 'RUB'  # Котируемая валюта
CRYPTO_CURRENCY = 'ETH'  # 
CAN_SPEND = 1000  # Сколько котируемой валюты готовы вложить в покупку по ордеру
# TODO Какое количество раз можно перезакупать
# TODO Предел для закупок
MARKUP = 0.002  # 0.001 = 0.1% - Какой навар со сделки хотим получать

STOCK_FEE = 0.002  # Какую комиссию берет биржа
PERIOD = 5  # Период в минутах для построения свечей
ORDER_BUY_LIFE_TIME = 0.5  # Через сколько минут отменять неисполненный ордер на покупку 0.5 = 30 сек.
# НЕ было данной переменной #######################
STOCK_TIME_OFFSET = 0  # Если расходится время биржи с текущим
# #################################################
USE_MACD = True  # True - оценивать тренд по MACD, False - покупать и продавать невзирая ни на что

BEAR_PERC = 70  # % что считаем поворотом при медведе (подробности - https://bablofil.ru/macd-python-stock-bot/
BULL_PERC = 99.9  # % что считаем поворотом при быке

# BEAR_PERC = 70  # % что считаем поворотом при медведе
# BULL_PERC = 100  # Так он будет продавать по минималке, как только курс пойдет вверх

API_URL = 'api.exmo.me'
API_VERSION = 'v1'

USE_LOG = False  # False
DEBUG = False  # True - выводить отладочную информацию, False - писать как можно меньше

numpy.seterr(all='ignore')

curr_pair = None

# Ордера на покупку
# conn = sqlite3.connect('example.db')
# c = conn.cursor()
#
# # Create table
# c.execute('''CREATE TABLE stocks
#              (date text, trans text, symbol text, qty real, price real)''')
#
# # Insert a row of data
# c.execute("INSERT INTO stocks VALUES ('2006-01-05','BUY','RHAT',100,35.14)")
#
# # Save (commit) the changes
# conn.commit()
#
# # We can also close the connection if we are done with it.
# # Just be sure any changes have been committed or they will be lost.
# conn.close()
#
# TODO fixture 3 buy
buy_orders = {}
buy_orders['one'] = {'order_id': '902953509', 'created': int(time.time()), 'type': 'buy', 'pair': 'ETH_RUB', 'quantity': '0.03314036', 'price': '28675.58999998', 'amount': '999.98992'}
# buy_orders['two'] = {'order_id': '802953509', 'created': '1528553554', 'type': 'buy', 'pair': 'ETH_RUB', 'quantity': '0.0127', 'price': '35800', 'amount': '993.6'}
# buy_orders['three'] = {'order_id': '702953509', 'created': '1528553554', 'type': 'buy', 'pair': 'ETH_RUB', 'quantity': '0.027', 'price': '36800', 'amount': '993.6'}
# buy_orders['four'] = {'order_id': '602953509', 'created': '1528553554', 'type': 'buy', 'pair': 'ETH_RUB', 'quantity': '0.027', 'price': '36800', 'amount': '993.6'}
# buy_orders['five'] = {'order_id': '602953509', 'created': '1528553554', 'type': 'buy', 'pair': 'ETH_RUB', 'quantity': '0.027', 'price': '36800', 'amount': '993.6'}

def buy_sum_all():
    """
        Проходим циклом по словарю и суммируем общую
    :return: Общая сумма
    """
    buy_sum_all_orders = {}
# CAN_SPEND = 1000 * на количество ордеров в течении
# buy_sum_all_orders = {}
# buy_sum_all_orders['all'] = {'order_id': '602953509', 'created': '1528553554', 'type': 'buy', 'pair': 'ETH_RUB', 'quantity': '0.027', 'price': '36800', 'amount': '993.6'}


buy_sum_all_amount_orders = CAN_SPEND * len(buy_orders)



# buy_orders.append(round(38040.89061547, 6))
# buy_orders.append(round(36631.4001, 6))
# buy_orders.append(round(36531.4001, 6))
# Ордера на продажу
sell_orders = {}
# order_id - идентификатор ордера
# created - дата и время создания ордера
# type - тип ордера
# pair - валютная пара
# price - цена по ордеру
# quantity - кол-во по ордеру
# amount - сумма по ордеру
# TODO fixture 3 sell
sell_orders['one'] = {'order_id': '1018342425', 'created': '1531937874', 'type': 'sell', 'pair': 'ETH_RUB', 'price': '30325.86308779', 'quantity': '0.03314036', 'amount': '1005.01002004'}

# Свой класс исключений
class ScriptError(Exception):
    pass


class ScriptQuitCondition(Exception):
    pass


# все обращения к API проходят через эту функцию
def call_api(api_method, http_method="POST", **kwargs):
    payload = {'nonce': int(round(time.time() * 1000))}

    if kwargs:
        payload.update(kwargs)
    payload = urllib.parse.urlencode(payload)

    H = hmac.new(key=API_SECRET, digestmod=hashlib.sha512)
    H.update(payload.encode('utf-8'))
    sign = H.hexdigest()

    headers = {"Content-type": "application/x-www-form-urlencoded", "Key": API_KEY, "Sign": sign}
    conn = http.client.HTTPConnection(API_URL, timeout=90)
    conn.request(http_method, "/" + API_VERSION + "/" + api_method, payload, headers)
    response = conn.getresponse().read()

    conn.close()

    try:
        obj = json.loads(response.decode('utf-8'))

        if 'error' in obj and obj['error']:
            raise ScriptError(obj['error'])
        return obj
    except json.decoder.JSONDecodeError:
        raise ScriptError('Ошибка анализа возвращаемых данных, получена строка', response)


# Получаем с биржи данные, необходимые для построения индикаторов
def get_ticks(pair):
    resource = requests.get('https://api.exmo.me/v1/trades/?pair=%s&limit=10000' % pair)
    data = json.loads(resource.text)

    chart_data = {}  # сформируем словарь с ценой закрытия по 5 минут
    for item in reversed(data[pair]):
        d = int(float(item['date']) / (PERIOD * 60)) * (PERIOD * 60)  # Округляем время сделки до PERIOD минут
        chart_data[d] = float(item['price'])
    return chart_data


# С помощью MACD делаем вывод о целесообразности торговли в данный момент (https://bablofil.ru/macd-python-stock-bot/)
def get_macd_advice(chart_data):
    macd, macdsignal, macdhist = talib.MACD(numpy.asarray([chart_data[item] for item in sorted(chart_data)]),
                                            fastperiod=12, slowperiod=26, signalperiod=9)

    idx = numpy.argwhere(numpy.diff(numpy.sign(macd - macdsignal)) != 0).reshape(-1) + 0
    inters = []

    for offset, elem in enumerate(macd):
        if offset in idx:
            inters.append(elem)
        else:
            inters.append(numpy.nan)
    trend = 'BULL' if macd[-1] > macdsignal[-1] else 'BEAR'
    hist_data = []
    max_v = 0
    growing = False
    for offset, elem in enumerate(macdhist):
        growing = False
        curr_v = macd[offset] - macdsignal[offset]
        if abs(curr_v) > abs(max_v):
            max_v = curr_v
        perc = curr_v / max_v

        if ((macd[offset] > macdsignal[offset] and perc * 100 > BULL_PERC)  # восходящий тренд
                or (
                        macd[offset] < macdsignal[offset] and perc * 100 < (100 - BEAR_PERC)
                )
        ):
            v = 1
            growing = True
        else:
            v = 0

        if offset in idx and not numpy.isnan(elem):
            # тренд изменился
            max_v = curr_v = 0  # обнуляем пик спреда между линиями
        hist_data.append(v * 1000)

    return ({'trend': trend, 'growing': growing})


# Выводит всякую информацию на экран, самое важное скидывает в Файл log.txt
def log(*args):
    if USE_LOG:
        l = open("./log_ETH_RUB_2.1.txt", 'a', encoding='utf-8')
        print(datetime.now(), *args, file=l)
        l.close()
    print(datetime.now(), ' ', *args)

# TODO Ф-ция для создания ФИКСТУР ордера на покупку
def create_fix_buy(pair):
    global USE_LOG
    USE_LOG = True
    log(pair, 'Создаем ордер на покупку')
    log(pair, 'Получаем текущие курсы')

    offers = call_api('order_book', pair=pair)[pair]
    try:
        current_rate =  float(offers['ask'][0][0]) # покупка по лучшей цене
        # current_rate = sum([float(item[0]) for item in offers['ask'][:3]]) / 3
        # покупка по средней цене из трех лучших в стакане
        can_buy = CAN_SPEND / current_rate
        # print('buy', can_buy, current_rate)
        log(pair, """
            Текущая цена - %0.8f
            На сумму %0.8f %s можно купить %0.8f %s
            Создаю ордер на покупку
            """ % (current_rate, CAN_SPEND, QUOTE_CURRENCY, can_buy, CRYPTO_CURRENCY)
            )
        # new_order = call_api(
        #     'order_create',
        #     pair=pair,
        #     quantity=can_buy,
        #     price=current_rate,
        #     type='buy'
        # )
        # log("Создан ордер на покупку order_id")
        # Запоминаем ордера на покупку CURRENCY_1
        #  TODO Записываем значение в конец множества словаря
        if len(buy_orders) == 0:
            buy_orders['one'] = {'order_id': '1021953509', 'created': int(time.time()), 'type': 'buy',
                                       'pair': pair, 'quantity': can_buy,
                                       'price': current_rate, 'amount': CAN_SPEND}
            log(pair, "Создан ордер на покупку %s %s" % (CRYPTO_CURRENCY, buy_orders['one']['order_id']))

        elif len(buy_orders) == 1:
            buy_orders['two'] = {'order_id': '2029535209', 'created': int(time.time()), 'type': 'buy',
                                       'pair': pair, 'quantity': can_buy,
                                       'price': current_rate, 'amount': CAN_SPEND}
            log(pair, "Создан ордер на покупку %s %s" % (CRYPTO_CURRENCY, buy_orders['two']['order_id']))

        elif len(buy_orders) == 2:
            buy_orders['three'] = {'order_id': '3029543509', 'created': int(time.time()), 'type': 'buy',
                                       'pair': pair, 'quantity': can_buy,
                                       'price': current_rate, 'amount': CAN_SPEND}
            log(pair, "Создан ордер на покупку %s %s" % (CRYPTO_CURRENCY, buy_orders['three']['order_id']))

        elif len(buy_orders) == 3:
            buy_orders['four'] = {'order_id': '4029533509', 'created': int(time.time()), 'type': 'buy',
                                   'pair': pair, 'quantity': can_buy,
                                   'price': current_rate, 'amount': CAN_SPEND}
            log(pair, "Создан ордер на покупку %s %s" % (CRYPTO_CURRENCY, buy_orders['four']['order_id']))

        elif len(buy_orders) == 4:
            buy_orders['five'] = {'order_id': '5029535039', 'created': int(time.time()), 'type': 'buy',
                                       'pair': pair, 'quantity': can_buy,
                                       'price': current_rate, 'amount': CAN_SPEND}
            log(pair, "Создан ордер на покупку %s %s" % (CRYPTO_CURRENCY, buy_orders['five']['order_id']))

    except ZeroDivisionError:
        print('Не удается вычислить цену', pair)
    USE_LOG = False


# Ф-ция для создания ордера на покупку
def create_buy(pair):
    global USE_LOG
    USE_LOG = True
    log(pair, 'Создаем ордер на покупку')
    log(pair, 'Получаем текущие курсы')

    offers = call_api('order_book', pair=pair)[pair]
    try:
        # current_rate =  float(offers['ask'][0][0]) # покупка по лучшей цене
        current_rate = sum([float(item[0]) for item in offers['ask'][:3]]) / 3
        # покупка по средней цене из трех лучших в стакане
        can_buy = CAN_SPEND / current_rate
        # print('buy', can_buy, current_rate)
        log(pair, """
            Текущая цена - %0.8f
            На сумму %0.8f %s можно купить %0.8f %s
            Создаю ордер на покупку
            """ % (current_rate, CAN_SPEND, QUOTE_CURRENCY, can_buy, CRYPTO_CURRENCY)
            )
        new_order = call_api(
            'order_create',
            pair=pair,
            quantity=can_buy,
            price=current_rate,
            type='buy'
        )
        log("Создан ордер на покупку %s" % new_order['order_id'])
        # Запоминаем ордера на покупку CURRENCY_1
        #  TODO Записываем значение в конец множества словаря
        if len(buy_orders) == 0:
            buy_orders['one'] = {'order_id': new_order['order_id'], 'created': time.time(), 'type': 'buy',
                                       'pair': pair, 'quantity': can_buy,
                                       'price': current_rate, 'amount': CAN_SPEND}
        elif len(buy_orders) == 1:
            buy_orders['two'] = {'order_id': new_order['order_id'], 'created': time.time(), 'type': 'buy',
                                       'pair': pair, 'quantity': can_buy,
                                       'price': current_rate, 'amount': CAN_SPEND}
        elif len(buy_orders) == 2:
            buy_orders['three'] = {'order_id': new_order['order_id'], 'created': time.time(), 'type': 'buy',
                                       'pair': pair, 'quantity': can_buy,
                                       'price': current_rate, 'amount': CAN_SPEND}
        elif len(buy_orders) == 3:
            buy_orders['four'] = {'order_id': new_order['order_id'], 'created': time.time(), 'type': 'buy',
                                   'pair': pair, 'quantity': can_buy,
                                   'price': current_rate, 'amount': CAN_SPEND}
        elif len(buy_orders) == 4:
            buy_orders['five'] = {'order_id': new_order['order_id'], 'created': time.time(), 'type': 'buy',
                                       'pair': pair, 'quantity': can_buy,
                                       'price': current_rate, 'amount': CAN_SPEND}
    except ZeroDivisionError:
        print('Не удается вычислить цену', pair)
    USE_LOG = False


# Ф-ция для создания ордера на продажу
def create_sell(pair):
    global USE_LOG
    USE_LOG = True
    balances = call_api('user_info')['balances']
    # if float(balances[CRYPTO_CURRENCY]) >= CURRENCY_1_MIN_QUANTITY: # Есть ли в наличии CURRENCY_1, которую можно продать?
    wanna_get = CAN_SPEND + CAN_SPEND * (STOCK_FEE + MARKUP)
    order_amount = float(balances[QUOTE_CURRENCY])
    new_rate = wanna_get / order_amount
    new_rate_fee = new_rate / (1 - STOCK_FEE)
    offers = call_api('order_book', pair=pair)[pair]
    current_rate = float(offers['bid'][0][0])  # Берем верхнюю цену, по которой кто-то покупает
    choosen_rate = current_rate if current_rate > new_rate_fee else new_rate_fee
    print('sell', balances[QUOTE_CURRENCY], wanna_get, choosen_rate)
    log(pair, """
    Итого на этот ордер было потрачено %0.8f %s, получено %0.8f %s
    Что бы выйти в плюс, необходимо продать купленную валюту по курсу %0.8f
    Тогда, после вычета комиссии %0.3f останется сумма %0.8f %s
    Итоговая прибыль составит %0.8f %s
    Текущий курс продажи %0.8f
    Создаю ордер на продажу по курсу %0.8f
    """
        % (
            CAN_SPEND, QUOTE_CURRENCY, order_amount, CRYPTO_CURRENCY,
            new_rate_fee,
            STOCK_FEE, (new_rate_fee * order_amount - new_rate_fee * order_amount * STOCK_FEE), QUOTE_CURRENCY,
            wanna_get, QUOTE_CURRENCY,
            current_rate,
            choosen_rate,
        ))
    new_order = call_api(
        'order_create',
        pair=pair,
        quantity=balances[CRYPTO_CURRENCY],
        price=choosen_rate,
        type='sell'
    )
    log(pair, "Создан ордер на продажу %s" % new_order['order_id'])
    # TODO  Запоминаем ордер на покупку CRYPTO_CURRENCY
    #  sell_orders.append(new_order)
    #  TODO Записываем значение в конец множества словаря
    # if len(sell_orders) == 0:
    #     sell_orders['one'] = {'order_id': new_order['order_id'], 'created': time.time(), 'type': 'sell',
    #                          'pair': pair, 'quantity': balances[CRYPTO_CURRENCY],
    #                          'price': choosen_rate, 'amount': wanna_get}
    if DEBUG:
        print('Создан ордер на продажу', QUOTE_CURRENCY, new_order['order_id'])
    USE_LOG = False

# def check_orders():
#     order_history = call_api('user_trades', pair=pair, limit=100)

# Бесконечный цикл процесса - основная логика
while True:
    try:
        for pair in MARKETS:  # Проходим по каждой паре из списка в начале
            try:  # Получаем список активных ордеров
                try:
                    # TODO Сверка в текущем словаре и на бирже
                    opened_orders = call_api('user_open_orders')[pair]
                    # print(opened_orders)
                    log(pair, "Проверяем ордера")
                    log(pair, "Ордера покупки")
                    print(buy_orders)
                    log(pair, "Ордера продажи")
                    print(sell_orders)
                except KeyError:
                    if DEBUG:
                        print('Открытых ордеров нет' + pair)
                        log(pair, "Открытых ордеров нет")
                    opened_orders = []
                # Есть ли неисполненные ордера на продажу pair?
                log(pair, " Обработка...")
                for order in opened_orders:
                    if order['type'] == 'sell':
                        # TODO В этом месте нужна проверка расхождения в цене в плюс или минус
                        try:
                            log(pair, "Получаем текущий курс")
                            offers = call_api('order_book', pair=pair)[pair]
                            current_rate = float(offers['ask'][0][0])  # покупка по лучшей цене
                            log(pair, "Покупка по лучшей цене %s" % current_rate)
                        except ZeroDivisionError:
                            print('Не удается вычислить цену', pair)
                            current_rate = 1000000
                        # Если цена изменилась и тренд пошёл вниз

                        if current_rate < float(order['price']):
                            for a in np.arange(0.01, 10, 0.01):  # Проходим в цикле
                                x = round(float(buy_orders['one']['price']), 6)  # Цена средневзвешанной цены по ордеру продажи
                                y = round(current_rate, 6)  # Текущая цена
                                z = x - ((x / 100) * a)
                                if round(z, 6) < round(y, 6):  # Сравниваем текущую цену с закупочной
                                    # print("На %s " % round(a, 6))
                                    log(
                                        """Цена изменилась на %s%% текущая цена - %s %s от первой %s %s""" %
                                          (round(a, 6), current_rate, QUOTE_CURRENCY, float(buy_orders['one']['price']),
                                           QUOTE_CURRENCY))
                                    break
                            # TODO Цена ниже на 0.5%, но не ниже 2%
                            for a in np.arange(0.01, 10, 0.01):  # Проходим в цикле
                                x = round(float(buy_orders['one']['price']), 6)  # Цена средневзвешанной цены по ордеру продажи
                                y = round(current_rate, 6)  # Текущая цена
                                z = x - ((x / 100) * a)
                                if round(z, 6) < round(y, 6):  # Сравниваем текущую цену с закупочной
                                    # print("На %s " % round(a, 6))
                                    log(pair, "Цена изменилась на %s%% "
                                              "текущая цена - %s %s от средневзвешанной %s %s"
                                        %
                                          (round(a, 6), current_rate, QUOTE_CURRENCY, float(order['price']),
                                           QUOTE_CURRENCY))
                                    if round(a, 6) > round(0.5, 6) or round(a, 6) < round(1.0, 6):
                                        log(pair, "Цена изменилась на 0.5%")
                                        # create_buy(pair=pair)
                                        if len(buy_orders) == 1:
                                            log(pair, "Докупаем...")
                                            # create_buy(pair=pair)
                                            # TODO fixture create buy two
                                            log(pair, "Ордер на покупку не достиг предела 2")
                                            log(pair, "Выставляем ордер на покупку")
                                            create_fix_buy(pair=pair)
                                            log(pair, "Проверяем полностью ли исполнен второй ордер")
                                            print(buy_orders['two'])
                                            # buy_orders.append(current_rate)
                                            break
                                        else:
                                            print("Ордер на покупку достиг предела 2")
                                            # print(buy_orders['two'])
                                    if round(a, 6) > round(1.0, 6) or round(a, 6) < round(1.5, 6):
                                        log(pair, "Цена изменилась на 1%")
                                        # create_buy(pair=pair)
                                        if len(buy_orders) == 2:
                                            log(pair, "Докупаем...")
                                            # create_buy(pair=pair)
                                            # TODO fixture create buy tree
                                            log(pair, "Ордер на покупку не достиг предела 3")
                                            log(pair, "Выставляем ордер на покупку")
                                            create_fix_buy(pair=pair)
                                            log(pair, "Проверяем полностью ли исполнен третий ордер")
                                            print(buy_orders['three'])
                                            # buy_orders.append(current_rate)
                                            break
                                        else:
                                            print("Ордер на покупку достиг предела 3")
                                    if round(a, 6) > round(1.5, 6) or round(a, 6) < round(2.0, 6):
                                        log(pair, "Цена изменилась на 1.5%")
                                        # create_buy(pair=pair)
                                        if len(buy_orders) == 3:
                                            log(pair, "Докупаем...")
                                            # create_buy(pair=pair)
                                            # TODO fixture create buy
                                            log(pair, "Ордер на покупку не достиг предела 4")
                                            log(pair, "Выставляем ордер на покупку")
                                            create_fix_buy(pair=pair)
                                            log(pair, "Проверяем полностью ли исполнен четвертый ордер")
                                            print(buy_orders['four'])
                                            # buy_orders.append(current_rate)
                                            break
                                        else:
                                            log(pair, "Ордер на покупку достиг предела 4")
                                        # buy_orders['two'] = {'order_id': '802953509', 'created': '1528553554',
                                        #                      'type': 'buy', 'pair': 'ETH_RUB', 'quantity': '0.0127',
                                        #                      'price': current_rate, 'amount': '993.6'}
                                    break
                            # TODO Зависимость 24 часа
                            # TODO Нужна общая сумма потраченного
                            start_time = sell_orders['one']['created']
                            log(pair, time.strftime("Время начала торговой сессии %d.%m %H:%M", time.localtime(int(start_time))))
                            log(pair, "Прошло 12 часов")
                            log(
                                """
                                Прошло 24 часа, принимаем решение на продажу всей валюты %0.8f %s по цене %0.8f %s,
                                на ордер было потрачено %0.8f %s.
                                Тогда, после вычета комиссии %0.3f%% останется сумма %0.8f %s
                                """
                                %
                                (float(sell_orders['one']['quantity']), CRYPTO_CURRENCY, current_rate, QUOTE_CURRENCY,
                                 buy_sum_all_amount_orders, QUOTE_CURRENCY,
                                STOCK_FEE, (float(sell_orders['one']['quantity']) * current_rate),
                                QUOTE_CURRENCY))
                            # print("Итого на этот ордер было потрачено %0.8f %s, получено %0.8f %s")
                            # print("Дата/время %s ордера на продажу" % time.asctime(current_time))
                            # TODO Проверка
                            # create_buy(pair=pair)
                            # print(buy_orders)
                            # orders_history = call_api('user_trades', pair=pair, limit=100)
                            # print(len(orders_history[pair]))
                            # for order_history in orders_history:
                            #
                            #     print(order_history)
                            # for buy_order in buy_orders:
                            #     # if buy_order == 'one':
                            #     #     print(buy_order)
                            #     #     print(buy_orders['one'])
                            #
                            #     if len(buy_orders) == 1:
                            #         # create_buy(pair=pair)
                            #         print("Ордер на покупку не достиг предела 1")
                            #         print("Выставляем ордер на покупку")
                            #         print(buy_orders['one'])
                            #         # buy_orders.append(current_rate)
                            #         break
                            #     elif len(buy_orders) == 2:
                            #         # create_buy(pair=pair)
                            #         print("Ордер на покупку не достиг предела 2")
                            #         print("Выставляем ордер на покупку")
                            #         print(buy_orders['two'])
                            #         # buy_orders.append(current_rate)
                            #         break
                            #     elif len(buy_orders) == 3:
                            #         # create_buy(pair=pair)
                            #         print("Ордер на покупку не достиг предела 3")
                            #         print("Выставляем ордер на покупку")
                            #         # buy_orders.append(current_rate)
                            #         break
                            #     elif len(buy_orders) == 4:
                            #         # create_buy(pair=pair)
                            #         print("Ордер на покупку не достиг предела 4")
                            #         print("Выставляем ордер на покупку")
                            #         # buy_orders.append(current_rate)
                            #         break
                            #     elif len(buy_orders) == 5:
                            #         # create_buy(pair=pair)
                            #         print("Ордер на покупку не достиг предела 5")
                            #         print("Выставляем ордер на покупку")
                            #         # buy_orders.append(current_rate)
                            #         break
                            #     else:  # Повторится то количество раз сколько было закупок
                            #         print("Ордера на покупку валюты нет")
                            #         print(buy_orders)
                            #         print(len(buy_orders))
                            # if current_rate >= float(order['price']) - (0.001 * float(order['price'])) or \
                            #         current_rate > float(order['price']) - (0.01 * float(order['price'])):


                                # TODO Цена ниже на 1%, но не ниже 1.5%. Делаем покупку на установленную сумму
                                # TODO CAN_SPEND, после исполнения ордера делаем отметку второй покупки
                                # for buy_order in buy_orders:
                                #     if len(buy_orders) == 1:
                                #         # create_buy(pair=pair)
                                #         print("Выставляем ордер на покупку")
                                #         buy_orders.append(current_rate)
                                #     else:
                                #         print("Ордера на покупку валюты нет")
                                #         print(buy_orders)
                                # TODO Проверяем, что ордер второй покупки исполнен. Отменяем ордер продажи
                                # TODO Назначаем новый ордер продажи
                            # elif current_rate >= float(order['price']) - (0.01 * float(order['price'])) or \
                            #         current_rate > float(order['price']) - (0.015 * float(order['price'])):
                            #     print("1%% Цена изменилась на %s от средневзвешанной %s, будем покупать ещё на %s" %
                            #           (current_rate, float(order['price']), CAN_SPEND))
                                # TODO Цена ниже на 3%
                                # TODO Цена ниже на 4%
                                # TODO Цена ниже на 5%
                            # else:
                            #     print("Цена изменилась на %s от средневзвешанной %s" %
                            #           (current_rate, float(order['price'])))
                        # TODO Если цена уменьшилась в соотношении в минус 1:2 процентов от цены навара,
                        # TODO сбиваем цену продажи в более выгодную сторону докупая ещё на ту же сумму,
                        # TODO если рынок позволяет MACD
                        #  Выводим в лог ордера на покупку CRYPTO_CURRENCY
                        # print(sell_orders)
                        print("1212", len(buy_orders))
                        # Есть неисполненные ордера на продажу pair, выход
                        raise ScriptQuitCondition('Выход, ждем пока не исполнятся/закроются все ордера на продажу (один'
                                                  ' ордер может быть разбит биржей на несколько и исполняться частями)')
                        # пропуск продажи
                        # pass
                    else:
                        # Запоминаем ордера на покупку CRYPTO_CURRENCY
                        sell_orders.append(order)
                        #  Выводим в лог ордера на покупку CRYPTO_CURRENCY
                        print(sell_orders)
                # Проверяем, есть ли открытые ордера на продажу CRYPTO_CURRENCY
                # открытые ордера есть
                if sell_orders:
                    for order in sell_orders:
                        # Проверяем, есть ли частично исполненные
                        if DEBUG:
                            print('Проверяем, что происходит с отложенным ордером', order['order_id'])
                        try:
                            order_history = call_api('order_trades', order_id=order['order_id'])
                            # по ордеру уже есть частичное выполнение, выход
                            raise ScriptQuitCondition('Выход, продолжаем надеяться докупить валюту по тому курсу, по ко'
                                                      'торому уже купили часть')
                        except ScriptError as e:
                            if 'Error 50304' in str(e):
                                if DEBUG:
                                    print('Частично исполненных ордеров нет')

                                time_passed = time.time() + STOCK_TIME_OFFSET * 60 * 60 - int(order['created'])

                                if time_passed > ORDER_BUY_LIFE_TIME * 60:
                                    log('Пора отменять ордер %s' % order)
                                    # Ордер уже давно висит, никому не нужен, отменяем
                                    call_api('order_cancel', order_id=order['order_id'])
                                    log('Ордер %s отменен' % order)
                                    # поменяли значение CURRENCY_1 на pair##########################
                                    raise ScriptQuitCondition('Отменяем ордер -за ' + str(ORDER_BUY_LIFE_TIME) +
                                                              ' минут не удалось купить ' + str(pair))
                                else:
                                    raise ScriptQuitCondition('Выход, продолжаем надеяться купить валюту по указанному '
                                                              'ранее курсу, со времени создания ордера прошло %s секунд'
                                                              % str(time_passed))
                            else:
                                raise ScriptQuitCondition(str(e))
                else:  # Открытых ордеров нет
                    balances = call_api('user_info')['balances']
                    reserved = call_api('user_info')['reserved']
                    min_quantity = call_api('pair_settings', pair=pair)[pair]
                    CURRENCY_1_MIN_QUANTITY = float(min_quantity['min_quantity'])
                    if float(balances[CRYPTO_CURRENCY]) >= CURRENCY_1_MIN_QUANTITY:
                        # Есть ли в наличии валюта CRYPTO_CURRENCY, которую можно продать?
                        print('Баланс: ' + str(float(balances[CRYPTO_CURRENCY])) + ' ' + str(CRYPTO_CURRENCY))
                        if USE_MACD:
                            macd_advice = get_macd_advice(chart_data=get_ticks(pair))
                            # проверяем, можно ли создать sell
                            if macd_advice['trend'] == 'BEAR' or (macd_advice['trend'] == 'BULL'
                                                                  and macd_advice['growing']):
                                print('Продавать нельзя, т.к. ситуация на рынке неподходящая: Трэнд ' +
                                      str(macd_advice['trend']) + '; Рост ' + str(macd_advice['growing']))
                                # log(pair, 'Для ордера %s не создаем ордер на продажу,
                                # т.к. ситуация на рынке неподходящая' % order['order_id'] )
                                # print(len(buy_orders))
                            else:
                                print('Выставляем ордер на продажу, т.к ситуация подходящая: ' +
                                      str(macd_advice['trend']) + ' ' + str(macd_advice['growing']))
                                log(pair, "Для выполненного ордера на покупку выставляем ордер на продажу")
                                create_sell(pair=pair)
                        else:  # создаем sell если тенденция рынка позволяет
                            log(pair, "Для выполненного ордера на покупку выставляем ордер на продажу")
                            create_sell(pair=pair)
                    else:
                        if float(balances[QUOTE_CURRENCY]) >= CAN_SPEND:
                            # log(pair, "Неисполненных ордеров нет, пора ли создать новый?")
                            # Проверяем MACD, если рынок в нужном состоянии, выставляем ордер на покупку
                            if USE_MACD:
                                macd_advice = get_macd_advice(chart_data=get_ticks(pair))
                                if macd_advice['trend'] == 'BEAR' and macd_advice['growing']:
                                    log(pair, "Создаем ордер на покупку")
                                    # create_buy(pair=pair)
                                    # TODO print(buy_orders[0])
                                    create_fix_buy(pair=pair)
                                    log(pair, "Проверяем полностью ли исполнен первый ордер")
                                    print(buy_orders['one'])
                                else:
                                    log(pair, "Условия рынка не подходят для торговли", macd_advice)

                            else:
                                log(pair, "Создаем ордер на покупку")
                                # create_buy(pair=pair)
                                # TODO print(buy_orders[0])
                                create_fix_buy(pair=pair)
                                log(pair, "Проверяем полностью ли исполнен первый ордер")
                                print(buy_orders['one'])
                        else:
                            order = str(' В ордере :' + str(float(reserved[CRYPTO_CURRENCY])) + '. ' + str(CRYPTO_CURRENCY)) \
                                if float(reserved[CRYPTO_CURRENCY]) > 0.0 else ''
                            raise ScriptQuitCondition('Не хватает денег для торговли: баланс ' + str(round(float(
                                balances[QUOTE_CURRENCY]))) + ' ' + str(QUOTE_CURRENCY) + order)
            except ScriptError as e:
                print(e)
            except ScriptQuitCondition as e:
                print(e)
            except Exception as e:
                print("!!!!", e)
        time.sleep(1)
    except Exception as e:
        print(e)
