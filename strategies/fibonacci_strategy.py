import pandas as pd
import numpy as np
from backtesting import Strategy

class FibonacciStrategy(Strategy):
    n_lookback = 50  # 고점/저점을 찾을 기간
    
    def init(self):
        # 1. 특정 기간 내 최고가와 최저가 탐색 (Indicator 등록)
        self.hh = self.I(lambda x: pd.Series(x).rolling(self.n_lookback).max().shift(1), self.data.High)
        self.ll = self.I(lambda x: pd.Series(x).rolling(self.n_lookback).min().shift(1), self.data.Low)

    def next(self):
        if np.isnan(self.hh[-1]) or np.isnan(self.ll[-1]):
            return

        # 피보나치 레벨 계산
        diff = self.hh[-1] - self.ll[-1]
        if diff == 0: return

        fib_382 = self.hh[-1] - diff * 0.382
        fib_500 = self.hh[-1] - diff * 0.500
        fib_618 = self.hh[-1] - diff * 0.618

        # 현재 주가 상태
        current_close = self.data.Close[-1]
        current_low = self.data.Low[-1]

        # 매수 조건: 
        # 1. 주가가 고점 대비 0.382 ~ 0.618 사이까지 내려왔을 때 (눌림목)
        # 2. 저가가 0.618 근처를 터치하거나 지지받고
        # 3. 당일 종가가 시가보다 높은 양봉일 때 (반등 신호)
        if fib_618 <= current_low <= fib_382:
            if current_close > self.data.Open[-1]:
                if not self.position:
                    self.buy()

        # 매도 조건: 
        # 1. 전고점(0.0 레벨) 근처 도달 시 익절
        if current_close >= self.hh[-1] * 0.98:
            if self.position:
                self.position.close()
        
        # 2. 0.786 레벨(깊은 조정) 이탈 시 손절
        fib_786 = self.hh[-1] - diff * 0.786
        if current_close < fib_786:
            if self.position:
                self.position.close()