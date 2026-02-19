import pandas as pd
import numpy as np
from backtesting import Strategy
from backtesting.lib import crossover

def RSI_Indicator(values, n=14):
    delta = pd.Series(values).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=n).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

class RsiDivergenceStrategy(Strategy):
    n_rsi = 14
    lookback = 30  # 과거 얼마만큼의 기간에서 고점/저점을 찾을 것인가
    
    def init(self):
        self.rsi = self.I(RSI_Indicator, self.data.Close, self.n_rsi)

    def next(self):
        if len(self.data.Close) < self.lookback + 5:
            return

        # --- 1. 상승 다이버전스 감지 (매수 신호) ---
        # 최근 5일 내에 RSI 저점이 형성되었는지 확인
        if self.rsi[-2] < self.rsi[-3] and self.rsi[-2] < self.rsi[-1] and self.rsi[-2] < 40:
            current_rsi_low = self.rsi[-2]
            current_price_low = self.data.Close[-2]
            
            # 그 이전의 저점 탐색 (lookback 범위 내)
            prev_rsi_low = None
            prev_price_low = None
            
            for i in range(5, self.lookback):
                idx = -i
                if self.rsi[idx] < self.rsi[idx-1] and self.rsi[idx] < self.rsi[idx+1]:
                    prev_rsi_low = self.rsi[idx]
                    prev_price_low = self.data.Close[idx]
                    break
            
            # 조건: 주가 저점은 낮아졌는데, RSI 저점은 높아졌을 때
            if prev_rsi_low and current_rsi_low > prev_rsi_low and current_price_low < prev_price_low:
                if not self.position:
                    self.buy()

        # --- 2. 하락 다이버전스 감지 (매도 신호) ---
        if self.rsi[-2] > self.rsi[-3] and self.rsi[-2] > self.rsi[-1] and self.rsi[-2] > 60:
            current_rsi_high = self.rsi[-2]
            current_price_high = self.data.Close[-2]
            
            prev_rsi_high = None
            prev_price_high = None
            
            for i in range(5, self.lookback):
                idx = -i
                if self.rsi[idx] > self.rsi[idx-1] and self.rsi[idx] > self.rsi[idx+1]:
                    prev_rsi_high = self.rsi[idx]
                    prev_price_high = self.data.Close[idx]
                    break
            
            # 조건: 주가 고점은 높아졌는데, RSI 고점은 낮아졌을 때
            if prev_rsi_high and current_rsi_high < prev_rsi_high and current_price_high > prev_price_high:
                if self.position:
                    self.position.close()