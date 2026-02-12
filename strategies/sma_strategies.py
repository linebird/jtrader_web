import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

# --- [전략 1] 이평선 기울기 반전 전략 ---
class SmaSlopeStrategy(Strategy):
    n1 = 20
    def init(self):
        close = pd.Series(self.data.Close)
        self.sma = self.I(lambda x: x.rolling(self.n1).mean(), close)

    def next(self):
        if len(self.sma) < 3: return
        curr_slope = self.sma[-1] - self.sma[-2]
        prev_slope = self.sma[-2] - self.sma[-3]
        if prev_slope < 0 and curr_slope > 0:
            if not self.position: self.buy()
        elif prev_slope > 0 and curr_slope < 0:
            if self.position: self.position.close()

# --- [전략 2] 이평선 골든크로스 전략 (5일/20일) ---
class SmaCrossStrategy(Strategy):
    n_fast = 5
    n_slow = 20
    def init(self):
        close = pd.Series(self.data.Close)
        self.sma_f = self.I(lambda x: x.rolling(self.n_fast).mean(), close)
        self.sma_s = self.I(lambda x: x.rolling(self.n_slow).mean(), close)

    def next(self):
        if crossover(self.sma_f, self.sma_s):
            self.buy()
        elif crossover(self.sma_s, self.sma_f):
            self.position.close()