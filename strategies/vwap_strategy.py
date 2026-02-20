import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

# --- VWAP 계산 함수 ---
def VWAP_Indicator(high, low, close, volume):
    """
    데일리 차트 기준 누적 VWAP 계산
    Typical Price = (High + Low + Close) / 3
    VWAP = Cumulative(Typical Price * Volume) / Cumulative(Volume)
    """
    typical_price = (high + low + close) / 3
    pv = typical_price * volume
    vwap = pv.cumsum() / volume.cumsum()
    return vwap

# --- VWAP 돌파 전략 클래스 ---
class VwapStrategy(Strategy):
    def init(self):
        # 고가, 저가, 종가, 거래량을 사용하여 VWAP 지표 등록
        self.vwap = self.I(
            VWAP_Indicator, 
            pd.Series(self.data.High), 
            pd.Series(self.data.Low), 
            pd.Series(self.data.Close), 
            pd.Series(self.data.Volume)
        )

    def next(self):
        # 매수 조건: 종가가 VWAP 라인을 상향 돌파할 때
        if crossover(self.data.Close, self.vwap):
            if not self.position:
                self.buy()

        # 매도 조건: 종가가 VWAP 라인을 하향 돌파할 때
        elif crossover(self.vwap, self.data.Close):
            if self.position:
                self.position.close()