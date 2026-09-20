import type { NewsResponse } from "@/lib/types";

interface NewsPanelProps {
  news: NewsResponse | null;
  loading: boolean;
}

export function NewsPanel({ news, loading }: NewsPanelProps) {
  return (
    <section className="news-section">
      <div className="news-heading">
        <div>
          <p className="kicker">MARKET NARRATIVE</p>
          <h2>市场新闻与情绪</h2>
        </div>
        {news ? (
          <span className={`analysis-mode ${news.analysis_mode}`}>
            {news.analysis_mode === "ai" ? "AI 分析" : "规则分析"}
          </span>
        ) : null}
      </div>
      {loading ? (
        <div className="news-loading">正在整理最新市场新闻…</div>
      ) : news?.articles.length ? (
        <>
          <div className="news-grid">
            {news.articles.map((article) => (
              <a className="news-card" href={article.url} target="_blank" rel="noreferrer" key={article.id}>
                <div className="news-card-meta">
                  <span className={`sentiment ${article.sentiment}`}>{article.sentiment_label}</span>
                  <time>{new Date(article.published_at).toLocaleDateString("zh-CN")}</time>
                </div>
                <h3>{article.title}</h3>
                <p>{article.summary}</p>
                <div className="news-card-footer">
                  <span>{article.source}</span>
                  <span>{article.related_symbols.join(" · ") || "MARKET"} ↗</span>
                </div>
              </a>
            ))}
          </div>
          <p className="news-notice">{news.notice}</p>
        </>
      ) : (
        <div className="news-loading">暂时没有相关新闻</div>
      )}
    </section>
  );
}
