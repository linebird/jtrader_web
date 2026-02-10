from backtesting import Backtest, Strategy
import pandas as pd


class SmaSlopeStrategy(Strategy):
    n1 = 20  # 이동평균 기간

    def init(self):
        # 20일 이동평균 계산 (self.I를 사용하여 지표 등록)
        close = pd.Series(self.data.Close)
        self.sma = self.I(lambda x: x.rolling(self.n1).mean(), close)

    def next(self):
        # 데이터가 충분하지 않으면 패스
        if len(self.sma) < 3:
            return

        # 기울기 계산: (현재 값 - 이전 값)
        curr_slope = self.sma[-1] - self.sma[-2]
        prev_slope = self.sma[-2] - self.sma[-3]

        # 매수 조건: 기울기가 음수에서 양수로 전환될 때 (하락 후 반등)
        if prev_slope < 0 and curr_slope > 0:
            if not self.position:
                self.buy()

        # 매도 조건: 기울기가 양수에서 음수로 전환될 때 (상승 후 꺾임)
        elif prev_slope > 0 and curr_slope < 0:
            if self.position:
                self.position.close()