import type { SystemReminder } from '../../pages/workstation/workstation.types';

type SystemRemindersProps = {
  reminders: SystemReminder[];
};

export function SystemReminders({ reminders }: SystemRemindersProps) {
  return (
    <section className="system-reminders" aria-labelledby="system-reminders-title">
      <div className="panel-title-row system-reminders__header">
        <h2 id="system-reminders-title">系统提醒</h2>
        <button className="link-action link-action--muted" type="button">
          查看全部
        </button>
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
                <button className="link-action" type="button">
                  {reminder.actionLabel}
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
