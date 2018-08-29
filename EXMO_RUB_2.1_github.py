import time
import json
import requests
import urllib, http.client
import hmac, hashlib

# Если нет нужных пакетов - читаем тут: https://bablofil.ru/python-indicators/
import numpy
import talib

from datetime import datetime
import numpy as np

VERSION = '2.0.2'

# Список пар, на которые торгуем
MARKETS = [
    # 'BTC_RUB',
    'ETH_RUB'
]

# QUOTE_CURRENCY
QUOTE_CURRENCY = 'RUB'  # Котируемая валюта

#
CRYPTO_CURRENCY = 'ETH'

CAN_SPEND = 5000  # Сколько готовы вложить в покупку
MARKUP = 0.001  # 0.001 = 0.1% - Какой навар со сделки хотим получать

STOCK_FEE = 0.002  # Какую комиссию берет биржа
PERIOD = 5  # Период в минутах для построения свечей
ORDER_LIFE_TIME = 3  # Через сколько минут отменять неисполненный ордер на покупку 0.5 = 30 сек.

USE_MACD = True  # True - оценивать тренд по MACD, False - покупать и продавать невзирая ни на что

BEAR_PERC = 70  # % что считаем поворотом при медведе (подробности - https://bablofil.ru/macd-python-stock-bot/
BULL_PERC = 99.9  # % что считаем поворотом при быке

# BEAR_PERC = 70  # % что считаем поворотом при медведе
# BULL_PERC = 100  # Так он будет продавать по минималке, как только курс пойдет вверх

API_URL = 'api.exmo.me'
API_VERSION = 'v1'

USE_LOG = True # (False)
DEBUG = True  # (False) True - выводить отладочную информацию, False - писать как можно меньше

numpy.seterr(all='ignore')

curr_pair = None


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

    headers = {"Content-type": "application/x-www-form-urlencoded",
               "Key": API_KEY,
               "Sign": sign}
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
                )):
            v = 1
            growing = True
        else:
            v = 0

        if offset in idx and not numpy.isnan(elem):
            # тренд изменился
            max_v = curr_v = 0  # обнуляем пик спреда между линиями
        hist_data.append(v * 1000)

    return {'trend': trend, 'growing': growing}


# Выводит всякую информацию на экран, самое важное скидывает в Файл log.txt
def log(*args):
    if USE_LOG:
        l = open("./log_" + pair + "_" + VERSION + ".txt", 'a', encoding='utf-8')
        print(datetime.now(), *args, file=l)
        l.close()
    print(datetime.now(), ' ', *args)


# Ф-ция для создания ордера на покупку
def create_buy(pair):
    global USE_LOG
    USE_LOG = True
    log(pair, 'Обработка...')
    log(pair, 'Создаем ордер на покупку')
    log(pair, 'Получаем текущие курсы')

    offers = call_api('order_book', pair=pair)[pair]
    try:
        # current_rate =  float(offers['bid'][0][0]) # покупка по лучшей цене
        current_rate = sum([float(item[0]) for item in offers['bid'][:1]]) + 3.0000001  # покупка по самой выгодной цене в стакане
        # current_rate = sum([float(item[0]) for item in offers['ask'][:3]]) / 3
        # покупка по средней цене из трех лучших в стакане
        can_buy = CAN_SPEND / current_rate
        print('buy', can_buy, current_rate)
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
        log(pair, "Создан ордер на покупку %s" % new_order['order_id'])
    except ZeroDivisionError:
        print('Не удается вычислить цену', pair)
    USE_LOG = False


# Ф-ция для создания ордера на продажу
def create_sell(pair):
    global USE_LOG
    USE_LOG = True
    balances = call_api('user_info')['balances']
    # if float(balances[CRYPTO_CURRENCY]) >= CURRENCY_1_MIN_QUANTITY: # Есть ли в наличии CURRENCY_1, которую можно продать?
    wanna_get = CAN_SPEND + CAN_SPEND * (STOCK_FEE + MARKUP)  # Сколько хочу получить 1000 + 1000 * (0.002 + 0.001)
    order_amount = float(balances[CRYPTO_CURRENCY])
    new_rate = wanna_get / order_amount  # 1000 + 1000 * (0.002 + 0.001)/ на то сколько купили
    new_rate_fee = new_rate / (1 - STOCK_FEE)  # (1000 + 1000 * (0.002 + 0.001)/ на то сколько купили) / (1 - 0.002)
    offers = call_api('order_book', pair=pair)[pair]
    current_rate = float(offers['bid'][0][0])  # Берем верхнюю цену, по которой кто-то покупает
    choosen_rate = current_rate if current_rate > new_rate_fee else new_rate_fee
    print('sell', balances[CRYPTO_CURRENCY], wanna_get, choosen_rate)
    log(pair, """
    Итого на этот ордер было потрачено %0.8f %s, получено %0.8f %s
    Что бы выйти в плюс, необходимо продать купленную валюту по курсу %0.8f
    Тогда, после вычета комиссии %0.4f останется сумма %0.8f %s
    Итоговая прибыль составит %0.8f %s
    Текущий курс продажи %0.8f
    Создаю ордер на продажу по курсу %0.8f
    """
        % (
            CAN_SPEND, QUOTE_CURRENCY, order_amount, CRYPTO_CURRENCY,
            new_rate_fee,
            STOCK_FEE, (new_rate_fee * order_amount - new_rate_fee * order_amount * STOCK_FEE), QUOTE_CURRENCY,
            (new_rate_fee * order_amount - new_rate_fee * order_amount * STOCK_FEE) - wanna_get, QUOTE_CURRENCY,
            current_rate,
            choosen_rate,
        )
        )
    new_order = call_api(
        'order_create',
        pair=pair,
        quantity=balances[CRYPTO_CURRENCY],
        price=choosen_rate,
        type='sell'
    )
    log(pair, "Создан ордер на продажу %s" % new_order['order_id'])
    print(new_order)
    if DEBUG:
        print('Создан ордер на продажу', CRYPTO_CURRENCY, new_order['order_id'])
    USE_LOG = False


def order_book_pair(pair):
    """
     Книга ордеров по валютной паре
    :param pair: Валютная пара
    :return: current_rate: текущая цена
    """
    global USE_LOG
    USE_LOG = True
    try:
        print(pair, "Получаем текущий курс")
        offers = call_api('order_book', pair=pair)[pair]
        current_rate = float(offers['ask'][0][0])  # покупка по лучшей цене
        return current_rate
    except ZeroDivisionError:
        print('Не удается вычислить цену', pair)
    USE_LOG = False


def change_minus(current_rate, order_price):
    """
        Функция вычисления процентной ставки для лучшей покупки по ордеру
        :param current_rate: текущая цена
        :param order_price: цена закупки
        :return:
    """
    for a in np.arange(0.0, 20, 0.01):
        x = round(float(order_price), 8)  # Цена закупки
        y = round(float(current_rate), 8)  # Текущая цена
        z = x - ((x / 100) * a)
        for b in np.arange(0.0, 100, 0.7):
            if round(a, 6) == round(b, 8):
                print("На %s%% цена %s " % (round(a, 8), round(z, 8)))
        if round(z, 6) < round(y, 6):  # Сравниваем текущую цену с закупочной
            print("Медвежий тренд, цена изменилась на %s%% и составляет %s" % (round(a, 8), round(z, 8)))
            break


def change_plus(current_rate, order_price):
    """
    Функция вычисления процентной ставки для лучшей продажи по ордеру
    :param current_rate: текущая цена
    :param order_price: цена закупки
    :return:
    """
    for a in np.arange(0.01, 100, 0.01):
        x = round(float(order_price), 8)  # Цена закупки
        y = round(float(current_rate), 8)  # Текущая цена
        z = x + ((x / 100) * a)
        for b in np.arange(0.1, 100, 0.1):
            if round(a, 8) == round(b, 8):
                print("На %s%% цена %s " % (round(a, 8), round(z, 8)))
        if round(z, 8) > round(y, 6):  # Сравниваем текущую цену с закупочной
            print("Бычий тренд, цена изменилась на %s%% и составляет %s " % (round(a, 8), round(z, 8)))
            break


def price_change(current_rate, order_price):
    if round(float(current_rate), 8) < round(float(order_price), 8):
        change_minus(current_rate, order_price)
    elif round(float(current_rate), 8) > round(float(order_price), 8):
        change_plus(current_rate, order_price)
    else:
        print('Цена не изменилась')


# Бесконечный цикл процесса - основная логика
while True:
    try:
        for pair in MARKETS:  # Проходим по каждой паре из списка в начале\
            try:
                print(pair, "Обработка...")
                try:
                    current_rate = order_book_pair(pair)
                    print(pair, "Цена на бирже %s %s" % (current_rate, QUOTE_CURRENCY))
                except ZeroDivisionError:
                    print('Не удается вычислить цену', pair)
                    current_rate = 1000000
                # Получаем список активных ордеров
                try:
                    print(pair, "Проверяем ордера")
                    opened_orders = call_api('user_open_orders')[pair]
                    print(pair, "Открытые ордера на бирже есть")
                    print(opened_orders)
                except KeyError:
                    if DEBUG:
                        print(pair, 'Открытых ордеров нет')
                        # log(pair, "Открытых ордеров нет")
                    opened_orders = []
                orders = []
                # Есть ли неисполненные ордера на продажу CURRENCY_1?
                for order in opened_orders:
                    if order['type'] == 'sell':
                        # Есть неисполненные ордера на продажу CURRENCY_1, выход
                        raise ScriptQuitCondition(
                            'Выход, ждем пока не исполнятся/закроются все ордера на продажу '
                            '(один ордер может быть разбит биржей на несколько и исполняться частями)'
                        )
                        # пропуск продажи
                        # pass
                    else:
                        # Запоминаем ордера на покупку CURRENCY_1
                        orders.append(order)
                # Проверяем, есть ли открытые ордера на покупку CURRENCY_1
                if orders:  # открытые ордера есть
                    for order in orders:
                        # Проверяем, есть ли частично исполненные
                        if DEBUG:
                            print('Проверяем, что происходит с отложенным ордером', order['order_id'])
                        try:
                            order_history = call_api('order_trades', order_id=order['order_id'])
                            # по ордеру уже есть частичное выполнение, выход
                            raise ScriptQuitCondition(
                                'Выход, продолжаем надеяться докупить валюту по тому курсу,'
                                ' по которому уже купили часть')
                        except ScriptError as e:
                            if 'Error 50304' in str(e):
                                if DEBUG:
                                    print('Частично исполненных ордеров нет')

                                time_passed = time.time() - int(order['created'])

                                if time_passed > ORDER_LIFE_TIME * 60:
                                    log('Пора отменять ордер %s' % order)
                                    # Ордер уже давно висит, никому не нужен, отменяем
                                    call_api('order_cancel', order_id=order['order_id'])
                                    log('Ордер %s отменен' % order)
                                    raise ScriptQuitCondition('Отменяем ордер -за ' + str(
                                        ORDER_LIFE_TIME) + ' минут не удалось купить ' + str(CRYPTO_CURRENCY))
                                else:
                                    raise ScriptQuitCondition(
                                        'Выход, продолжаем надеяться купить валюту по указанному ранее курсу, со времени создания ордера прошло %s секунд' % str(
                                            time_passed))
                            else:
                                raise ScriptQuitCondition(str(e))
                else:  # Открытых ордеров нет
                    balances = call_api('user_info')['balances']
                    reserved = call_api('user_info')['reserved']
                    min_quantity = call_api('pair_settings', pair=pair)[pair]
                    CURRENCY_1_MIN_QUANTITY = float(min_quantity['min_quantity'])
                    if float(balances[CRYPTO_CURRENCY]) >= CURRENCY_1_MIN_QUANTITY:  # Есть ли в наличии CURRENCY_1, которую можно продать?
                        print('Баланс: ' + str(float(balances[CRYPTO_CURRENCY])) + ' ' + str(CRYPTO_CURRENCY))
                        if USE_MACD:
                            macd_advice = get_macd_advice(
                                chart_data=get_ticks(pair))  # проверяем, можно ли создать sell
                            if macd_advice['trend'] == 'BEAR' or (
                                    macd_advice['trend'] == 'BULL' and macd_advice['growing']):
                                print('Продавать нельзя, т.к. ситуация на рынке неподходящая: Трэнд ' + str(
                                    macd_advice['trend']) + '; Рост ' + str(macd_advice['growing']))
                                # log(pair, 'Для ордера %s не создаем ордер на продажу, т.к. ситуация на рынке неподходящая' % order['oreder_id'] )
                            else:
                                print('Выставляем ордер на продажу, т.к ситуация подходящая: ' + str(
                                    macd_advice['trend']) + ' ' + str(macd_advice['growing']))
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
                                    create_buy(pair=pair)
                                else:
                                    print(pair, "Условия рынка не подходят для торговли", macd_advice)
                            else:
                                log(pair, "Создаем ордер на покупку")
                                create_buy(pair=pair)
                        else:
                            order = str(
                                ' В ордере :' + str(float(reserved[CRYPTO_CURRENCY])) + '. ' + str(CRYPTO_CURRENCY)) if float(
                                reserved[CRYPTO_CURRENCY]) > 0.0 else ''
                            raise ScriptQuitCondition('Не хватает денег для торговли: баланс ' + str(
                                round(float(balances[QUOTE_CURRENCY]))) + ' ' + str(QUOTE_CURRENCY) + order)
            except ScriptError as e:
                print(e)
            except ScriptQuitCondition as e:
                print(e)
            except Exception as e:
                print("!!!!", e)
        time.sleep(5)
    except Exception as e:
        print(e)