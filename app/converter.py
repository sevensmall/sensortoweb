# encoding=utf-8
import serial
import binascii
import datetime
import time
import copy
import math
import numpy as np


CHR_DELIM = 0xA5
CHR_EDELIM = 0xC3
CHR_ACK = 'A'
CHR_SETUP = 'S'
CHR_RECEVIE ='R'

chip = 2

if chip == 1:
    CP = -1040384
    BP = 33.8281374553667
    AP = -1.55337412640767E-05

    CT = 1.05353412945952
    BT = -8.7228131962035E-06
    AT = 5.59473006378368E-11

    CA = 3120224
    BA = 40.4235810419019
elif chip == 2:
# #　渡してくれたソースコードでOPT加算したの定数を使っております
#　140928送付したサンプルのＯＴＰから計算した値に修正

#　平均と3σは以下のテーブルの通り
#	係数	平均		3σ
#	AP		-1.53E-05	1.38E-05
#	BP		3.37E+01	6.42E+00
#	CP		←OTP書き込みのそのままの値を使う
#	AT		9.64E-11	6.56E-11
#	BT		-9.41E-06	1.45E-06
#	CT		1.06E+00	7.56E-03
#	BA		4.18E+01	1.94E+00
#	CA		←OTP書き込みのそのままの値を使う
#	
#	140928送付したサンプルのＯＴＰ読み値
#	AP		F209
#	BP		017C
#	CP		41C2
#	AT		F2C8
#	BT		1C37
#	CT		E1A6
#	BA		49A0
#	CA		EE2F
#	
#　以下計算結果と計算式

    CP = -1160000
    #  この数値を使用してください 
    BP = 3.377445296E+01
    #  = HEX2DEC(017C) * 6.42E+00 / 32767 + 3.37E+01
    AP = -1.680563066E-05
    #  = (HEX2DEC(F209) - 65536) * 1.38E-05 / 32767 + (-1.53E-05)

    CT = 1.058207306E+00
    #  = (HEX2DEC(E1A6) - 65536) * 7.56E-03 / 32767 + 1.06E+00
    BT = -9.090368969E-06
    #  = HEX2DEC(1C37) * 1.45E-06 / 32767 + (-9.41E-06)
    AT = 8.962518387E-11
    #  = (HEX2DEC(F2C8) - 65536) * 6.56E-11 / 32767 + 9.64E-11

    CA = 3100000
    #  この数値を使用してください
    BA = 4.29159E+01
#  = HEX2DEC(49A0) * 1.94E+00 / 32767 + 4.18E+01

PRES_HP0 = 1013.25    # hPa in 0m of sea-surface
PRES_TNOM = 273.15    # degC to Kelvin
PRES_HDEN = 0.0065   # denominator of Height
PRES_PDEN = 5.257;     # denominator of Pressure

Tnow = 25.0
Hnow = 0.0

presArrary = []

def conv24bit(buf):
    s = (buf[0] << 16) + (buf[1] << 8) + buf[2]
    return s

def conv16bit(buf):
    s = (buf[0] << 8) + buf[1];
    return s


def movingaverage(x, window):
    y = np.empty(len(x)-window+1)
    for i in range(len(y)):
        y[i] = np.sum(x[i:i+window])/window
    return y

def convPa(pkt):
    Dt = pkt['dptat']
    Dp = pkt['dpres']

    wk = BP * BP - (4 * AP * (CP - Dp))
    Pl = ( -1.0 * BP + math.sqrt(math.fabs(wk))) / (2 * AP)

    Tr = (Dt -CA) / BA

    Po = Pl / (AT * Tr * Tr + BT * Tr + CT)


    return Pl, Tr/256, Po

def meterFromPa(pa):
    hpa = pa/100
    ret = math.pow(PRES_HP0 / hpa, 1 / PRES_PDEN) - 1
    ret = ret * (Tnow + PRES_TNOM)
    ret = ret / PRES_HDEN + Hnow
    return ret

def skipToDelim(seq):
    while(len(seq) > 0):
        if seq[0] == CHR_DELIM:
            return True
        seq.pop(0)
        return False

def checkPenalty(seq):
    mPenalty += 1
    if mPenalty >= mPenaltyMax:
        seq = []
    return None

def parseRecPkt(pkt, buf):
    now = datetime.datetime.now()
    pkt['time'] = now.strftime("%A, %d. %B %Y %I:%M:%S%p")
    pkt['dpres'] = getPres(buf)
    pkt['dptat'] = getTemp(buf)
    if len(buf) >= 1:
        pkt['sensor'] = buf[0]
        buf.pop(0)
    if len(buf) >= 1:
        pkt['data'] =buf[1]
        buf.pop(0)
    pkt['pl'],pkt['temp'], pkt['pres'] = convPa(pkt)

    return pkt
    # print pkt

def getPres(buf):
    ret = 0
    if len(buf) < 0:
        return ret
    if len(buf) >= 3:
        ret = conv24bit(buf)
    for i in xrange(0,3):
        buf.pop(0)
    return ret

def getTemp(buf):
    ret = 0
    if len(buf) < 2:
        return ret
    if len(buf) >= 2:
        ret = conv16bit(buf)
        ret <<= 8
    for i in xrange(0,2):
        buf.pop(0)
    return ret

def parsePkt(seq):
    ret = skipToDelim(seq)
    if not ret:
        return None

    if len(seq) < 3:
        checkPenalty(seq)
        return None

    pkt = {}
    pkt['delim'] = seq[0]
    n = seq[1]
    pkt['datalen'] = seq[1]
    pkt['type'] = chr(seq[2])

    if len(seq) < (n + 2):
        checkPenalty(seq)
        return None

    mPenalty = 0
    seq.pop(0)
    seq.pop(0)
    seq.pop(0)


    if pkt['type'] == CHR_RECEVIE:
        parseRecPkt(pkt, seq)
    elif pkt['type'] == CHR_ACK:
        # parseAckPkt
        pass
    else:
        i = 0
        while i < len(pkt) and len(seq) > 0:
            d += seq[0]
            i += 1
            seq.pop(0)
        print d
        return None

    if len(seq) >= 1:
        pkt['chksum'] = seq[0]
        seq.pop(0)

    if len(seq) >= 1:
        if seq[0] == int(CHR_EDELIM):
            seq.pop(0)

    return pkt

