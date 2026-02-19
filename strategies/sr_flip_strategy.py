import pandas as pd
import numpy as np
from backtesting import Strategy

class SrFlipStrategy(Strategy):
    n_lookback = 20  # 박스권 상단을 정의할 기간
    retest_threshold = 0.005  # 리테스트로 인정할 오차 범위 (0.5%)

    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        # 과거 n일 동안의 최고가 (저항선) 계산
        self.resistance = self.I(lambda x: x.rolling(self.n_lookback).max().shift(1), high)
        self.state = "IDLE"  # IDLE -> BREAKOUT -> RETEST -> LONG
        self.breakout_level = 0

    def next(self):
        # 1. 돌파 감지 (IDLE -> BREAKOUT)
        if self.state == "IDLE":
            if self.data.Close[-1] > self.resistance[-1]:
                self.state = "BREAKOUT"
                self.breakout_level = self.resistance[-1]

        # 2. 리테스트 감지 (BREAKOUT -> RETEST)
        elif self.state == "BREAKOUT":
            lower_bound = self.breakout_level * (1 - self.retest_threshold)
            upper_bound = self.breakout_level * (1 + self.retest_threshold)
            
            if self.data.Low[-1] <= upper_bound:
                if self.data.Close[-1] >= lower_bound:
                    self.state = "RETEST"
            
            if self.data.Close[-1] < self.breakout_level * 0.97:
                self.state = "IDLE"

        # 3. 반등 시 매수 (RETEST -> LONG)
        elif self.state == "RETEST":
            if self.data.Close[-1] > self.breakout_level:
                self.buy()
                self.state = "LONG"

        # 4. 청산 조건 (LONG -> IDLE)
        elif self.state == "LONG":
            # 포지션이 없으면 상태 초기화
            if not self.position:
                self.state = "IDLE"
                return

            # [수정된 핵심 부분] 
            # self.position.entry_price 대신 self.trades[0].entry_price 사용
            # 현재 열려 있는 거래들(trades) 중 첫 번째 거래의 진입가를 가져옵니다.
            entry_price = self.trades[0].entry_price

            # 손절: 전 저항선(지지선)을 종가로 2% 이상 이탈 시
            if self.data.Close[-1] < self.breakout_level * 0.98:
                self.position.close()
                self.state = "IDLE"
            
            # 익절: 진입가 대비 10% 수익 시
            elif self.data.Close[-1] > entry_price * 1.10:
                self.position.close()
                self.state = "IDLE"