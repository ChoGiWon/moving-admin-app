importScripts('https://www.gstatic.com/firebasejs/10.8.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.8.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyCFHnunxUTOV38tcsVWjTxrsMQ8JLNW6BA",
  projectId: "moving-admin-push",
  messagingSenderId: "969733949330",
  appId: "1:969733949330:web:31960e4db0a0225b47a34b"
});

const messaging = firebase.messaging();

// 백그라운드 메시지 수신 시 직접 알림 띄우기 (data 페이로드 우선 참조)
messaging.onBackgroundMessage(function(payload) {
  console.log('[sw.js] 백그라운드 메시지 수신:', payload);
  
  const title = (payload.data && payload.data.title) || (payload.notification && payload.notification.title) || "🚨 새로운 이삿짐 견적 접수!";
  const body = (payload.data && payload.data.body) || (payload.notification && payload.notification.body) || "";
  const targetUrl = (payload.data && payload.data.url) || 'https://prime-express.duckdns.org/admin';

  const options = {
    body: body,
    icon: "/static/logo-main.png",
    badge: "/static/logo-main.png",
    data: { url: targetUrl }
  };

  self.registration.showNotification(title, options);
});

// 알림 클릭 시 관리자 페이지 창 열기 또는 포커스
self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || 'https://prime-express.duckdns.org/admin';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
      // 1. 이미 열려 있는 관리자 창이 있는지 확인 후 포커스
      for (let i = 0; i < clientList.length; i++) {
        let client = clientList[i];
        if (client.url.includes('/admin') && 'focus' in client) {
          return client.focus();
        }
      }
      // 2. 열려 있는 창이 없다면 새로 관리자 창 열기
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});