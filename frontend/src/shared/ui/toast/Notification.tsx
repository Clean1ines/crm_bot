import { useNotificationStore } from '@/shared/lib/notification/useNotifications';

export const Notification = () => {
  const notifications = useNotificationStore((s) => s.notifications);
  const remove = useNotificationStore((s) => s.removeNotification);

  return (
    <div className="fixed top-5 right-5 z-50 space-y-2">
      {notifications.map(n => (
        <div
          key={n.id}
          className={`notification ${n.type === 'error' ? 'error' : ''}`}
          onClick={() => remove(n.id)}
        >
          {n.message}
        </div>
      ))}
    </div>
  );
};
