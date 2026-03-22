import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=4, height=3, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.fig.patch.set_facecolor('#1E1E1E')
        self.axes = self.fig.add_subplot(111)
        self.axes.set_facecolor('#1E1E1E')
        
        # Modern subtle axes
        self.axes.tick_params(colors='#A0A0A0', labelsize=9)
        self.axes.yaxis.label.set_color('#A0A0A0')
        self.axes.xaxis.label.set_color('#A0A0A0')
        self.axes.title.set_color('#ffffff')
        self.axes.title.set_fontsize(13)
        self.axes.title.set_fontweight('bold')
        
        for spine in self.axes.spines.values():
             spine.set_visible(False)
             
        self.fig.subplots_adjust(left=0.15, right=0.95, top=0.85, bottom=0.20)
        super(MplCanvas, self).__init__(self.fig)
