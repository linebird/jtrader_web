import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

def RSI_Indicator(values, n=14):
    delta = pd.Series(values).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=n).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

class RsiSupportStrategy(Strategy):
    n_rsi = 14
    n_fast = 20
    n_slow = 60

    def init(self):
        close = pd.Series(self.data.Close)
        self.rsi = self.I(RSI_Indicator, close, self.n_rsi)
        self.sma20 = self.I(lambda x: x.rolling(self.n_fast).mean(), close)
        self.sma60 = self.I(lambda x: x.rolling(self.n_slow).mean(), close)

    def next(self):
        # 1. 상승장 필터: 20일선이 60일선 위에 있는 정배열 상태
        is_bull_market = self.sma20[-1] > self.sma60[-1]
        
        # 2. RSI 지지 확인: RSI가 40~50 사이의 '눌림' 구간에 위치
        rsi_in_support_zone = 40 <= self.rsi[-1] <= 50
        
        # 3. 반등 신호: 전일 종가보다 오늘 종가가 상승 (양봉/반등 확인)
        price_rebound = self.data.Close[-1] > self.data.Open[-1]

        # 매수 조건
        if is_bull_market and rsi_in_support_zone and price_rebound:
            if not self.position:
                self.buy()

        # 매도 조건: RSI가 70(과매수)을 돌파하거나, 60일선을 하향 이탈할 때(추세 붕괴)
        elif self.rsi[-1] >= 70 or crossover(self.sma60, self.data.Close):
            if self.position:
                self.position.close()