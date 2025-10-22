const { app, BrowserWindow, Menu, Tray, nativeImage, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow;
let tray;
let isAlwaysOnTop = false;
let backendProcess = null;
let healthCheckInterval = null;

// 后端服务管理
function startBackendService() {
  return new Promise((resolve, reject) => {
    try {
      const pythonPath = process.platform === 'win32' ? 'python' : 'python3';
      const backendPath = path.join(__dirname, '../app/main.py');
      
      console.log('启动Python后端服务...');
      backendProcess = spawn(pythonPath, [backendPath], {
        cwd: path.join(__dirname, '..'),
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
      });

      let backendPort = 8090; // 默认端口
      
      backendProcess.stdout.on('data', (data) => {
        const output = data.toString().trim();
        console.log(`[后端] ${output}`);
        
        // 检测端口信息
        const portMatch = output.match(/starting on http:\/\/127\.0\.0\.1:(\d+)/);
        if (portMatch) {
          backendPort = parseInt(portMatch[1]);
          console.log(`检测到后端服务端口: ${backendPort}`);
        }
      });

      backendProcess.stderr.on('data', (data) => {
        console.error(`[后端错误] ${data.toString().trim()}`);
      });

      backendProcess.on('error', (error) => {
        console.error('后端服务启动失败:', error);
        reject(error);
      });

      backendProcess.on('exit', (code) => {
        console.log(`后端服务退出，代码: ${code}`);
        backendProcess = null;
      });

      // 等待服务启动并检测端口
      setTimeout(async () => {
        try {
          // 尝试多个可能的端口
          let port = null;
          for (let p = 8090; p <= 8099; p++) {
            try {
              port = await checkBackendHealth(p);
              console.log(`后端服务启动成功，端口: ${port}`);
              resolve(port);
              return;
            } catch (e) {
              continue;
            }
          }
          throw new Error('无法连接到后端服务');
        } catch (error) {
          console.error('后端服务健康检查失败:', error);
          reject(error);
        }
      }, 3000);

    } catch (error) {
      console.error('启动后端服务时出错:', error);
      reject(error);
    }
  });
}

function stopBackendService() {
  return new Promise((resolve) => {
    if (backendProcess) {
      console.log('正在停止后端服务...');
      backendProcess.kill('SIGTERM');
      
      // 等待进程退出
      const timeout = setTimeout(() => {
        if (backendProcess) {
          console.log('强制终止后端服务');
          backendProcess.kill('SIGKILL');
        }
        resolve();
      }, 5000);

      backendProcess.on('exit', () => {
        clearTimeout(timeout);
        backendProcess = null;
        console.log('后端服务已停止');
        resolve();
      });
    } else {
      resolve();
    }
  });
}

function checkBackendHealth(port = 8090) {
  return new Promise((resolve, reject) => {
    const req = http.get(`http://127.0.0.1:${port}/`, (res) => {
      if (res.statusCode === 200) {
        resolve(port);
      } else {
        reject(new Error(`HTTP ${res.statusCode}`));
      }
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.setTimeout(3000, () => {
      req.destroy();
      reject(new Error('健康检查超时'));
    });
  });
}

function detectBackendPort() {
  return new Promise((resolve) => {
    // 尝试多个可能的端口
    let port = null;
    let attempts = 0;
    const maxAttempts = 10;
    
    const tryPort = (p) => {
      if (attempts >= maxAttempts) {
        resolve(null);
        return;
      }
      
      checkBackendHealth(p).then(foundPort => {
        resolve(foundPort);
      }).catch(() => {
        attempts++;
        tryPort(p + 1);
      });
    };
    
    tryPort(8090);
  });
}

function startHealthCheck() {
  if (healthCheckInterval) {
    clearInterval(healthCheckInterval);
  }

  healthCheckInterval = setInterval(async () => {
    try {
      // 尝试多个可能的端口
      let port = null;
      for (let p = 8090; p <= 8099; p++) {
        try {
          port = await checkBackendHealth(p);
          break;
        } catch (e) {
          continue;
        }
      }
      
      if (!port) {
        throw new Error('无法连接到后端服务');
      }
    } catch (error) {
      console.warn('后端服务健康检查失败，尝试重启...', error.message);
      try {
        await stopBackendService();
        await startBackendService();
      } catch (restartError) {
        console.error('重启后端服务失败:', restartError);
        // 显示错误对话框
        if (mainWindow) {
          mainWindow.webContents.send('backend-error', {
            message: '后端服务连接失败',
            details: restartError.message,
            suggestion: '请检查Python环境和依赖是否正确安装'
          });
        }
      }
    }
  }, 10000); // 每10秒检查一次
}

function createWindow() {
  // 创建无边框窗口
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    frame: false, // 无边框
    titleBarStyle: 'hidden',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      preload: path.join(__dirname, 'preload.js'),
      webSecurity: true
    },
    icon: path.join(__dirname, 'icon.png'),
    show: false, // 先不显示，等加载完成
    backgroundColor: '#0b0e14'
  });

  // 加载播放器页面
  const indexPath = path.join(__dirname, '../web/index.html');
  mainWindow.loadFile(indexPath);
  
  // 等待页面加载完成后设置后端端口
  mainWindow.webContents.once('dom-ready', () => {
    // 尝试检测后端服务端口
    detectBackendPort().then(port => {
      if (port) {
        mainWindow.webContents.executeJavaScript(`
          window.BACKEND_PORT = ${port};
          console.log('设置后端端口:', ${port});
        `);
      }
    }).catch(err => {
      console.error('检测后端端口失败:', err);
    });
  });

  // 窗口加载完成后显示
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    
    // 开发模式下打开开发者工具
    if (process.argv.includes('--dev')) {
      mainWindow.webContents.openDevTools();
    }
  });

  // 窗口关闭事件
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 创建系统托盘
  createTray();

  // 创建菜单
  createMenu();
}

function createTray() {
  // 创建托盘图标
  const iconPath = path.join(__dirname, 'icon.png');
  const trayIcon = nativeImage.createFromPath(iconPath);
  
  tray = new Tray(trayIcon.resize({ width: 16, height: 16 }));
  
  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示窗口',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      }
    },
    {
      label: '置顶切换',
      click: () => {
        toggleAlwaysOnTop();
      }
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        app.quit();
      }
    }
  ]);
  
  tray.setContextMenu(contextMenu);
  tray.setToolTip('MultipleLive Desktop Player');
  
  // 双击托盘图标显示窗口
  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

function createMenu() {
  const template = [
    {
      label: '文件',
      submenu: [
        {
          label: '退出',
          accelerator: 'CmdOrCtrl+Q',
          click: () => {
            app.quit();
          }
        }
      ]
    },
    {
      label: '视图',
      submenu: [
        {
          label: '置顶切换',
          accelerator: 'CmdOrCtrl+T',
          click: () => {
            toggleAlwaysOnTop();
          }
        },
        {
          label: '全屏',
          accelerator: 'F11',
          click: () => {
            if (mainWindow) {
              mainWindow.setFullScreen(!mainWindow.isFullScreen());
            }
          }
        },
        { type: 'separator' },
        {
          label: '最小化到托盘',
          accelerator: 'CmdOrCtrl+M',
          click: () => {
            if (mainWindow) {
              mainWindow.hide();
            }
          }
        }
      ]
    },
    {
      label: '帮助',
      submenu: [
        {
          label: '关于',
          click: () => {
            shell.openExternal('https://github.com/your-repo/multipleLive');
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function toggleAlwaysOnTop() {
  if (mainWindow) {
    isAlwaysOnTop = !isAlwaysOnTop;
    mainWindow.setAlwaysOnTop(isAlwaysOnTop);
    
    // 更新菜单标签
    const menu = Menu.getApplicationMenu();
    const viewMenu = menu.items.find(item => item.label === '视图');
    if (viewMenu && viewMenu.submenu) {
      const topMostItem = viewMenu.submenu.items.find(item => item.label === '置顶切换');
      if (topMostItem) {
        topMostItem.label = isAlwaysOnTop ? '取消置顶' : '置顶切换';
      }
    }
  }
}

// IPC 通信处理
ipcMain.handle('window-minimize', () => {
  if (mainWindow) {
    mainWindow.minimize();
  }
});

ipcMain.handle('window-maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.handle('window-close', () => {
  if (mainWindow) {
    mainWindow.hide(); // 隐藏到托盘而不是关闭
  }
});

ipcMain.handle('window-toggle-always-on-top', () => {
  toggleAlwaysOnTop();
});

ipcMain.handle('window-toggle-fullscreen', () => {
  if (mainWindow) {
    mainWindow.setFullScreen(!mainWindow.isFullScreen());
  }
});

// 应用事件
app.whenReady().then(async () => {
  try {
    // 先启动后端服务
    await startBackendService();
    // 启动健康检查
    startHealthCheck();
    // 创建窗口
    createWindow();
  } catch (error) {
    console.error('应用启动失败:', error);
    // 显示错误对话框
    const { dialog } = require('electron');
    dialog.showErrorBox('启动失败', `无法启动后端服务: ${error.message}\n\n请检查:\n1. Python环境是否正确安装\n2. 依赖包是否已安装 (pip install -r requirements.txt)\n3. 端口8090是否被占用`);
    app.quit();
  }
});

app.on('window-all-closed', async () => {
  // 在 macOS 上，除非用户用 Cmd + Q 确定地退出，
  // 否则绝大部分应用及其菜单栏会保持激活。
  if (process.platform !== 'darwin') {
    // 停止健康检查
    if (healthCheckInterval) {
      clearInterval(healthCheckInterval);
      healthCheckInterval = null;
    }
    // 停止后端服务
    await stopBackendService();
    app.quit();
  }
});

app.on('activate', () => {
  // 在 macOS 上，当单击 dock 图标并且没有其他窗口打开时，
  // 通常在应用程序中重新创建窗口。
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// 应用退出前清理
app.on('before-quit', async (event) => {
  event.preventDefault();
  
  // 停止健康检查
  if (healthCheckInterval) {
    clearInterval(healthCheckInterval);
    healthCheckInterval = null;
  }
  
  // 停止后端服务
  await stopBackendService();
  
  // 真正退出
  app.exit(0);
});

// 防止多实例运行
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    // 当运行第二个实例时，将焦点放到主窗口
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}
