import os
from flask import Flask
from routes.stock_routes import stock_bp
from routes.ticker_routes import ticker_bp
from routes.etf_routes import etf_bp

app = Flask(__name__)

# 블루프린트 등록
# url_prefix를 지정하면 해당 라우트의 모든 주소 앞에 붙습니다.
app.register_blueprint(stock_bp, url_prefix='/')      # 메인 백테스트 화면
app.register_blueprint(ticker_bp) # /ticker 경로 활성화
app.register_blueprint(etf_bp)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host='0.0.0.0', port=port)