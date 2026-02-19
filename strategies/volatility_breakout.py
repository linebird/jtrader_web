import pandas as pd
import numpy as np
from backtesting import Strategy

class VolatilityBreakout(Strategy):
    k = 0.5 

    def init(self):
        # 1. 전일 고가와 전일 저가를 지표(Indicator)로 등록
        # self.I로 감싸야 next()에서 [-1] 로 접근이 가능합니다.
        self.prev_high = self.I(lambda x: pd.Series(x).shift(1), self.data.High)
        self.prev_low = self.I(lambda x: pd.Series(x).shift(1), self.data.Low)

        # 2. 변동폭(Range) 계산도 지표로 등록
        self.v_range = self.I(lambda h, l: h - l, self.prev_high, self.prev_low)

    def next(self):
        # 첫 번째 날 등 데이터가 부족하여 NaN인 경우 계산 방지
        if np.isnan(self.v_range[-1]):
            return

        # 이제 self.v_range[-1]은 '현재 시점의 전일 변동폭'을 의미합니다.
        target_price = self.data.Open[-1] + (self.v_range[-1] * self.k)

        # 매수 조건: 현재가가 타겟가를 돌파
        if self.data.High[-1] >= target_price:
            if not self.position:
                self.buy(limit=target_price)

        # 다음 날 시가 매도 (포지션이 있다면 매일 종가에 청산 명령 -> 다음 날 시가 체결)
        if self.position:
            self.position.close()