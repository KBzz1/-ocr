import type { SystemReminder } from '../../pages/workstation/workstation.types';
import { appRoutes } from '../../app/routes';

type SystemRemindersProps = {
  reminders: SystemReminder[];
};

export function SystemReminders({ reminders }: SystemRemindersProps) {
  return (
    <section className="system-reminders" aria-labelledby="system-reminders-title">
      <div className="panel-title-row system-reminders__header">
        <h2 id="system-reminders-title">系统提醒</h2>
        <a className="link-action link-action--muted" href={appRoutes.tasks.path}>
          查看全部
        </a>
      </div>

      <div className="system-reminders__list">
        {reminders.map((reminder) => (
          <article className="reminder-item" key={reminder.id}>
            <span className={`reminder-item__dot reminder-item__dot--${reminder.tone}`} aria-hidden="true" />
            <div>
              <div className="reminder-item__header">
                <h3>{reminder.title}</h3>
                <time>{reminder.timeText}</time>
              </div>
              <p>{reminder.message}</p>
              {reminder.actionLabel ? (
                <a className="link-action" href={appRoutes.tasks.path}>
                  {reminder.actionLabel}
                </a>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
