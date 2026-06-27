const { request } = require("../../utils/api");

Page({
  data: {
    loading: true,
    products: [],
    portfolio: null,
    chartOptions: [],
    annualOptions: [],
    annualOptionIndex: 0,
    selectedAnnual: null,
    chartOptionIndex: 0,
    selectedSeries: "portfolio",
    activeSeriesLabel: "FOF组合净值曲线",
    activeSeries: [],
    error: "",
    sections: {
      metrics: true,
      annual: false,
      curve: false,
      positions: false,
      products: false,
    },
  },

  onLoad() {
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData().finally(() => wx.stopPullDownRefresh());
  },

  async loadData() {
    this.setData({ loading: true, error: "" });
    try {
      const [products, portfolio] = await Promise.all([
        request("/api/products"),
        request("/api/portfolio"),
      ]);
      const chartOptions = [
        { value: "portfolio", label: "FOF组合净值曲线" },
        ...((portfolio.positions || []).map((item) => ({
          value: item.product_key,
          label: `${item.product_name || item.product_key}净值曲线`,
        }))),
      ];
      const annualOptions = (portfolio.annual_returns || []).map((item) => ({
        value: String(item.year),
        label: `${item.year} 年`,
        return: item.return,
      }));
      this.setData({
        products,
        portfolio,
        chartOptions,
        annualOptions,
        annualOptionIndex: 0,
        selectedAnnual: annualOptions[0] || null,
        chartOptionIndex: 0,
        selectedSeries: "portfolio",
        activeSeriesLabel: chartOptions[0]?.label || "FOF组合净值曲线",
        activeSeries: portfolio.series || [],
        loading: false,
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: "数据加载失败，请确认后端服务和网络已连接。",
      });
    }
  },

  formatPct(value) {
    if (value === null || value === undefined) {
      return "-";
    }
    return `${(value * 100).toFixed(2)}%`;
  },

  onSeriesChange(event) {
    const chartOptionIndex = Number(event.detail.value || 0);
    const selectedSeries = (this.data.chartOptions[chartOptionIndex] || {}).value || "portfolio";
    const portfolio = this.data.portfolio || {};
    const activeSeries = selectedSeries === "portfolio"
      ? (portfolio.series || [])
      : ((portfolio.product_series && portfolio.product_series[selectedSeries]) || []);
    this.setData({
      chartOptionIndex,
      selectedSeries,
      activeSeriesLabel: (this.data.chartOptions[chartOptionIndex] || {}).label || "FOF组合收益曲线",
      activeSeries,
    });
  },

  onAnnualChange(event) {
    const annualOptionIndex = Number(event.detail.value || 0);
    const selectedAnnual = this.data.annualOptions[annualOptionIndex] || null;
    this.setData({
      annualOptionIndex,
      selectedAnnual,
    });
  },

  toggleSection(event) {
    const key = event.currentTarget.dataset.key;
    if (!key) {
      return;
    }
    this.setData({
      [`sections.${key}`]: !this.data.sections[key],
    });
  },
});
