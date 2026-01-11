import pandas as pd
import mplfinance as mpf
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

# 모듈에서 로직 가져오기
from modules import technical 

class RealTimeChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.info_label = QLabel("종목을 선택해주세요.")
        self.info_label.setStyleSheet("background-color: #34495E; color: white; font-weight: bold; font-size: 12pt; padding: 5px;")
        self.layout.addWidget(self.info_label)

        # 캔버스 설정
        self.fig = Figure(figsize=(10, 8), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.layout.addWidget(self.canvas)
        
        # 스타일
        self.mc = mpf.make_marketcolors(up='red', down='blue', inherit=True)
        self.style = mpf.make_mpf_style(marketcolors=self.mc, gridstyle=':', y_on_right=True)

        self.df = None
        self.current_ticker = None
        
        # 차트 설정 (나중에 설정 화면과 연동)
        self.chart_settings = {
            'ma_periods': [5, 20, 50, 100, 200],
            'fractal': True,
            'bollinger': False # 필요 시 True로 변경
        }

    def load_data(self, ticker, df, change_rate=0.0):
        self.current_ticker = ticker
        
        # 모듈화
        # df는 원본을 건드리지 않기 위해 복사본 사용 권장하나 여기선 직접 전달
        self.df = technical.process_chart_data(df, self.chart_settings)
        
        # Date 인덱스 이름 보장
        self.df.index.name = 'Date'
        
        self.update_plot()
        
        if not self.df.empty:
            last_price = self.df['Close'].iloc[-1]
            self.update_header_info(last_price, change_rate)

    def update_header_info(self, price, change_rate):
        color_code = "#FF0000" if change_rate > 0 else "#0000FF" if change_rate < 0 else "#FFFFFF"
        
        ma_text = ""
        if self.df is not None and not self.df.empty:
            last_row = self.df.iloc[-1]
            ma_vals = []
            for d in self.chart_settings['ma_periods']:
                col = f'MA{d}'
                if col in self.df.columns and not pd.isna(last_row[col]):
                    ma_vals.append(f"MA{d}:${last_row[col]:,.2f}")
            ma_text = " | ".join(ma_vals)

        self.info_label.setText(
            f"종목: {self.current_ticker} | 현재가: ${price:,.2f} | <span style='color:{color_code}'>등락률: {change_rate:+.2f}%</span><br>"
            f"<span style='font-size:10pt; color:#BDC3C7;'>{ma_text}</span>"
        )

    def update_plot(self):
        if self.df is None or self.df.empty: return

        self.fig.clear()
        
        # [Painter 로직 이식]
        
        # 1. 축 구성 (Main 3 : Volume 1)
        gs = self.fig.add_gridspec(2, 1, height_ratios=[3, 1])
        ax1 = self.fig.add_subplot(gs[0])
        
        has_volume = 'Volume' in self.df.columns and self.df['Volume'].sum() > 0
        ax2 = self.fig.add_subplot(gs[1], sharex=ax1) if has_volume else None

        # 2. AddPlots 구성
        add_plots = []
        
        # A. 이동평균선
        ma_colors = {5:'black', 20:'orange', 50:'blue', 100:'green', 200:'red'}
        for d in self.chart_settings['ma_periods']:
            col = f'MA{d}'
            if col in self.df.columns:
                color = ma_colors.get(d, 'gray')
                add_plots.append(mpf.make_addplot(self.df[col], color=color, width=1.0, ax=ax1))

        # B. 프랙탈
        if 'Fractal_Up' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Fractal_Up'], type='scatter', markersize=50, marker='v', color='blue', ax=ax1))
        if 'Fractal_Down' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Fractal_Down'], type='scatter', markersize=50, marker='^', color='red', ax=ax1))

        # C. 볼린저 밴드 (옵션)
        if 'BBU' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['BBU'], color='green', linestyle=':', width=1.0, ax=ax1))
            add_plots.append(mpf.make_addplot(self.df['BBL'], color='green', linestyle=':', width=1.0, ax=ax1))

        # 3. 그리기
        try:
            mpf.plot(
                self.df, 
                type='candle', 
                style=self.style, 
                ax=ax1, 
                volume=ax2, 
                addplot=add_plots if add_plots else None,
                warn_too_much_data=10000
            )
            
            if ax1: ax1.set_ylabel("")
            if ax2: ax2.set_ylabel("")
            self.canvas.draw()
            
        except Exception as e:
            print(f"Plot Error: {e}")

    def update_realtime_price(self, price):
        if self.df is None or self.df.empty: return

        last_idx = self.df.index[-1]
        
        current_h = self.df.at[last_idx, 'High']
        current_l = self.df.at[last_idx, 'Low']
        
        self.df.at[last_idx, 'Close'] = price
        self.df.at[last_idx, 'High'] = max(current_h, price)
        self.df.at[last_idx, 'Low'] = min(current_l, price)
        
        # 실시간 업데이트 시에도 모듈을 통해 지표 재계산
        self.df = technical.process_chart_data(self.df, self.chart_settings)
        self.update_plot()