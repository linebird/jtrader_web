import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

# --- RSI 계산 함수 ---
def RSI_Indicator(values, n=14):
    """
    RSI (Relative Strength Index) 계산
    """
    delta = pd.Series(values).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=n).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# --- RSI 전략 클래스 ---
class RsiStrategy(Strategy):
    n_rsi = 14
    rsi_low = 30   # 과매도 기준 (매수 타이밍)
    rsi_high = 70  # 과매수 기준 (매도 타이밍)

    def init(self):
        # RSI 지표 등록
        self.rsi = self.I(RSI_Indicator, self.data.Close, self.n_rsi)

    def next(self):
        # 매수 조건: RSI가 30선을 상향 돌파할 때 (과매도 탈출)
        if crossover(self.rsi, self.rsi_low):
            if not self.position:
                self.buy()

        # 매도 조건: RSI가 70선을 하향 돌파할 때 (과매수 진입 후 꺾임)
        elif crossover(self.rsi_high, self.rsi):
            if self.position:
                self.position.close()