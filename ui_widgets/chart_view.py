import pandas as pd
import mplfinance as mpf
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
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
        
        # 차트 설정
        self.chart_settings = {
            'ma_periods': [5, 20, 50, 100, 200],
            'fractal': True,
            'bollinger': False,
            'alligator': True # [신규] 엘리게이터 활성화
        }

    def load_data(self, ticker, df, change_rate=0.0):
        self.current_ticker = ticker
        
        # 모듈화: 데이터 가공 (Alligator 컬럼도 여기서 계산됨)
        self.df = technical.process_chart_data(df, self.chart_settings)
        self.df.index.name = 'Date'
        
        self.update_plot()
        
        if not self.df.empty:
            last_price = self.df['Close'].iloc[-1]
            self.update_header_info(last_price, change_rate)

    def update_header_info(self, price, change_rate):
        color_code = "#FF0000" if change_rate > 0 else "#0000FF" if change_rate < 0 else "#FFFFFF"
        
        # 상단 헤더에는 깔끔하게 가격 정보만 표시 (지표 정보는 범례로 이동)
        self.info_label.setText(
            f"종목: {self.current_ticker} | 현재가: ${price:,.2f} | <span style='color:{color_code}'>등락률: {change_rate:+.2f}%</span>"
        )

    def format_volume(self, x, pos):
        if x >= 1e6: return f'{x*1e-6:.1f}M'
        elif x >= 1e3: return f'{x*1e-3:.0f}K'
        return f'{int(x)}'

    def update_plot(self):
        if self.df is None or self.df.empty: return

        self.fig.clear()
        
        # 1. 축 구성 (Main 3 : Volume 1)
        gs = self.fig.add_gridspec(2, 1, height_ratios=[3, 1])
        ax1 = self.fig.add_subplot(gs[0])
        
        has_volume = 'Volume' in self.df.columns and self.df['Volume'].sum() > 0
        ax2 = self.fig.add_subplot(gs[1], sharex=ax1) if has_volume else None

        # 2. AddPlots 구성
        add_plots = []
        legend_handles = []
        
        # A. 이동평균선 (MA)
        ma_colors = {5:'black', 20:'orange', 50:'gray', 100:'lightgray', 200:'silver'} 
        # (엘리게이터와 색상 겹침 방지를 위해 MA 색상을 무채색 계열로 조정하거나 유지 가능. 여기선 가독성 위해 조정)
        
        for d in self.chart_settings['ma_periods']:
            col = f'MA{d}'
            if col in self.df.columns:
                color = ma_colors.get(d, 'gray')
                # 굵기를 얇게 하여 엘리게이터와 구분
                add_plots.append(mpf.make_addplot(self.df[col], color=color, width=0.8, ax=ax1))
                legend_handles.append(Line2D([0], [0], color=color, linewidth=1.5, label=f'MA {d}'))

        # B. 엘리게이터 (Alligator) [신규 추가]
        # Jaw(Blue), Teeth(Red), Lips(Green)
        if 'Alligator_Jaw' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Alligator_Jaw'], color='blue', width=1.5, ax=ax1))
            legend_handles.append(Line2D([0], [0], color='blue', linewidth=1.5, label='Jaw(13,8)'))

        if 'Alligator_Teeth' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Alligator_Teeth'], color='red', width=1.5, ax=ax1))
            legend_handles.append(Line2D([0], [0], color='red', linewidth=1.5, label='Teeth(8,5)'))

        if 'Alligator_Lips' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Alligator_Lips'], color='green', width=1.5, ax=ax1))
            legend_handles.append(Line2D([0], [0], color='green', linewidth=1.5, label='Lips(5,3)'))

        # C. 프랙탈
        if 'Fractal_Up' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Fractal_Up'], type='scatter', markersize=50, marker='v', color='purple', ax=ax1))
        if 'Fractal_Down' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Fractal_Down'], type='scatter', markersize=50, marker='^', color='magenta', ax=ax1))

        # D. 볼린저 밴드
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
            
            # 범례 추가 (좌측 상단)
            if legend_handles:
                ax1.legend(handles=legend_handles, loc='upper left', fontsize='small', framealpha=0.6)

            if ax2:
                ax2.yaxis.set_major_formatter(FuncFormatter(self.format_volume))
                ax2.set_ylabel("Vol")

            if ax1: ax1.set_ylabel("")
            
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
        
        # 실시간 업데이트 시 지표 재계산
        self.df = technical.process_chart_data(self.df, self.chart_settings)
        self.update_plot()