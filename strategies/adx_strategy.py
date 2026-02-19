import pandas as pd
import numpy as np
from backtesting import Strategy
from backtesting.lib import crossover

# --- ADX 및 DI 지표 계산 함수 ---
def ADX_Indicator(high, low, close, n=14):
    """ADX, +DI, -DI를 계산하여 반환"""
    tr = pd.DataFrame(index=close.index)
    tr['h-l'] = high - low
    tr['h-pc'] = abs(high - close.shift(1))
    tr['l-pc'] = abs(low - close.shift(1))
    tr['tr'] = tr[['h-l', 'h-pc', 'l-pc']].max(axis=1)

    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)

    # Wilder's Smoothing (EMA와 유사)
    atr = tr['tr'].ewm(alpha=1/n, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/n, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/n, adjust=False).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/n, adjust=False).mean()
    
    return adx, plus_di, minus_di

# --- ADX 전략 클래스 ---
class AdxStrategy(Strategy):
    n = 14
    adx_threshold = 25  # 추세 강도 기준 (보통 25 이상이면 강한 추세)

    def init(self):
        # 고가, 저가, 종가 데이터를 바탕으로 지표 등록
        self.adx, self.plus_di, self.minus_di = self.I(
            ADX_Indicator, 
            pd.Series(self.data.High), 
            pd.Series(self.data.Low), 
            pd.Series(self.data.Close), 
            self.n
        )

    def next(self):
        # 매수 조건: ADX > 25 (강한 추세) 이고, +DI가 -DI를 골든크로스 할 때
        if self.adx[-1] > self.adx_threshold:
            if crossover(self.plus_di, self.minus_di):
                if not self.position:
                    self.buy()

        # 매도/청산 조건: -DI가 +DI를 골든크로스 하거나 추세가 약해질 때(ADX 하락)
        if crossover(self.minus_di, self.plus_di):
            if self.position:
                self.position.close()