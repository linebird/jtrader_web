import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

# --- MACD 계산 함수 ---
def MACD_Indicator(values, n_fast=12, n_slow=26, n_signal=9):
    """
    MACD Line, Signal Line, Histogram을 계산하여 반환
    """
    close_ser = pd.Series(values)
    fast_ema = close_ser.ewm(span=n_fast, adjust=False).mean()
    slow_ema = close_ser.ewm(span=n_slow, adjust=False).mean()
    
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=n_signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

# --- MACD 전략 클래스 ---
class MacdStrategy(Strategy):
    n_fast = 12
    n_slow = 26
    n_signal = 9

    def init(self):
        # 지표 등록
        self.macd, self.signal, self.hist = self.I(
            MACD_Indicator, self.data.Close, self.n_fast, self.n_slow, self.n_signal
        )

    def next(self):
        # 매수 조건: MACD 라인이 Signal 라인을 골든크로스 할 때
        if crossover(self.macd, self.signal):
            if not self.position:
                self.buy()

        # 매도 조건: MACD 라인이 Signal 라인을 데드크로스 할 때
        elif crossover(self.signal, self.macd):
            if self.position:
                self.position.close()