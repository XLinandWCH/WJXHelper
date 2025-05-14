from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService

# 使用你的 msedgedriver.exe 的绝对路径
driver_path = r"C:\Users\xlina\Desktop\WJXHelper\msedgedriver.exe"

try:
    print(f"尝试使用驱动: {driver_path}")
    service = EdgeService(executable_path=driver_path)
    driver = webdriver.Edge(service=service)
    driver.get("https://www.bing.com")
    print(f"成功打开 Bing, 页面标题: {driver.title}")
    driver.quit()
    print("浏览器已关闭。")
except Exception as e:
    print(f"发生错误: {e}")