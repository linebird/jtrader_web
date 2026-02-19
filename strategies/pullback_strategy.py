import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

class SmaPullbackStrategy(Strategy):
    n_fast = 20
    n_slow = 60
    
    def init(self):
        # 지표 계산
        close = pd.Series(self.data.Close)
        self.sma20 = self.I(lambda x: x.rolling(self.n_fast).mean(), close)
        self.sma60 = self.I(lambda x: x.rolling(self.n_slow).mean(), close)

    def next(self):
        # 1. 상승 추세 필터: 주가가 60일선 위에 있고, 20일선이 60일선 위에 있을 때 (정배열)
        is_uptrend = self.data.Close[-1] > self.sma60[-1] and self.sma20[-1] > self.sma60[-1]
        
        # 2. 눌림목 감지: 저가가 20일선에 닿거나 하회함 (터치)
        price_touched_sma20 = self.data.Low[-1] <= self.sma20[-1]
        
        # 3. 반등 확인: 종가가 20일선 위에서 마감
        price_above_sma20 = self.data.Close[-1] > self.sma20[-1]

        # 매수 조건
        if is_uptrend and price_touched_sma20 and price_above_sma20:
            if not self.position:
                self.buy()

        # 매도 조건: 20일 이평선을 종가 기준으로 확실히 이탈(데드크로스)할 때
        elif crossover(self.sma20, self.data.Close):
            if self.position:
                self.position.close()