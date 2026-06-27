const app = getApp();

function request(path) {
  return new Promise((resolve, reject) => {
    const headers = {};
    if (app.globalData.accessCode) {
      headers["X-FOF-Access-Code"] = app.globalData.accessCode;
    }
    wx.request({
      url: `${app.globalData.apiBase}${path}`,
      method: "GET",
      header: headers,
      success: (res) => {
        if (res.statusCode >= 400) {
          reject(new Error((res.data && res.data.error) || "请求失败"));
          return;
        }
        resolve(res.data);
      },
      fail: reject,
    });
  });
}

module.exports = {
  request,
};
