"use client";

import { useState } from "react";

import { translateNews } from "@/lib/api";
import type { NewsResponse, NewsTranslation } from "@/lib/types";

interface NewsPanelProps {
  news: NewsResponse | null;
  loading: boolean;
}

export function NewsPanel({ news, loading }: NewsPanelProps) {
  const [translations, setTranslations] = useState<Record<string, NewsTranslation>>({});
  const [visibleTranslations, setVisibleTranslations] = useState<Record<string, boolean>>({});
  const [translatingId, setTranslatingId] = useState<string | null>(null);
  const [translationError, setTranslationError] = useState<string | null>(null);

  const toggleTranslation = async (articleId: string, title: string, summary: string) => {
    if (translations[articleId]) {
      setVisibleTranslations((current) => ({ ...current, [articleId]: !current[articleId] }));
      return;
    }

    setTranslatingId(articleId);
    setTranslationError(null);
    try {
      const translation = await translateNews(title, summary);
      setTranslations((current) => ({ ...current, [articleId]: translation }));
      setVisibleTranslations((current) => ({ ...current, [articleId]: true }));
    } catch (reason) {
      setTranslationError(reason instanceof Error ? reason.message : "翻译暂时不可用");
    } finally {
      setTranslatingId(null);
    }
  };

  return (
    <section className="news-section">
      <div className="news-heading">
        <div>
          <p className="kicker">MARKET NARRATIVE · 中英双语</p>
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
            {news.articles.map((article) => {
              const translation = translations[article.id];
              const showTranslation = visibleTranslations[article.id] && translation;
              return (
                <article className="news-card" key={article.id}>
                  <div className="news-card-meta">
                    <span className={`sentiment ${article.sentiment}`}>{article.sentiment_label}</span>
                    <time>{new Date(article.published_at).toLocaleDateString("zh-CN")}</time>
                  </div>
                  <div className="news-language-label">{showTranslation ? "中文译文" : "ENGLISH ORIGINAL"}</div>
                  <h3>{showTranslation ? translation.title_zh : article.title}</h3>
                  <p>{showTranslation ? translation.summary_zh : article.summary}</p>
                  <div className="news-actions">
                    <button
                      type="button"
                      onClick={() => void toggleTranslation(article.id, article.title, article.summary)}
                      disabled={translatingId === article.id}
                    >
                      {translatingId === article.id ? "翻译中…" : showTranslation ? "显示英文" : "中文翻译"}
                    </button>
                    <a href={article.url} target="_blank" rel="noreferrer">阅读原文 ↗</a>
                  </div>
                  <div className="news-card-footer">
                    <span>{article.source}</span>
                    <span>{article.related_symbols.join(" · ") || "MARKET"}</span>
                  </div>
                </article>
              );
            })}
          </div>
          {translationError ? <p className="news-notice translation-error">{translationError}</p> : null}
          <p className="news-notice">{news.notice} · 新闻译文由机器生成，请以英文原文为准。</p>
        </>
      ) : (
        <div className="news-loading">暂时没有相关新闻</div>
      )}
    </section>
  );
}
