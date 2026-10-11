type AppLoaderProps = { label?: string };

export function AppLoader({ label = '\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430\u2026' }: AppLoaderProps) {
  return (
    <div className="app-loader" role="status" aria-live="polite">
      <section className="app-loader-card">
        <div className="loader-vessel" aria-hidden="true">
          <span className="loader-vessel-neck" />
          <span className="loader-vessel-body">
            <span className="loader-vessel-scale loader-vessel-scale-a" />
            <span className="loader-vessel-scale loader-vessel-scale-b" />
            <span className="loader-vessel-scale loader-vessel-scale-c" />
            <span className="loader-vessel-liquid"><i /></span>
          </span>
          <span className="loader-vessel-foot" />
          <span className="loader-vessel-pipe" />
          <span className="loader-vessel-lamp" />
        </div>
        <div className="app-loader-kicker">{'\u041e\u0420\u0411\u0418\u0422\u0410'}</div>
        <strong>{label}</strong>
        <span className="app-loader-caption">{'\u0417\u0430\u043f\u043e\u043b\u043d\u044f\u0435\u043c \u0442\u0435\u0445\u043d\u043e\u043b\u043e\u0433\u0438\u0447\u0435\u0441\u043a\u0443\u044e \u0451\u043c\u043a\u043e\u0441\u0442\u044c \u0438 \u043f\u043e\u0434\u0433\u0433\u043e\u0442\u0430\u0432\u043b\u0438\u0432\u0430\u0435\u043c \u0434\u0430\u043d\u043d\u044b\u0435'}</span>
      </section>
    </div>
  );
}
