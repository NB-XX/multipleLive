const { app, BrowserWindow, Menu, Tray, nativeImage, ipcMain, shell } = require('electron');
const path = require('path');

let mainWindow;
let tray;
let isAlwaysOnTop = false;

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
app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  // 在 macOS 上，除非用户用 Cmd + Q 确定地退出，
  // 否则绝大部分应用及其菜单栏会保持激活。
  if (process.platform !== 'darwin') {
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
