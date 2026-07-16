import React from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './styles.module.css';

export interface SlidesProps {
  /** Path to the deck HTML, relative to the site root, e.g. "decks/00-introduction.html" */
  src: string;
  /** Label shown on the toolbar */
  title?: string;
}

/**
 * Embeds a self-contained reveal.js explainer deck (served from /static/decks/)
 * as a responsive 16:9 inline player, with a link to open it fullscreen in a new tab.
 * Each deck carries its own reveal.js + styles, so it is fully isolated from the docs theme.
 */
export default function Slides({src, title = 'Slides'}: SlidesProps): JSX.Element {
  const url = useBaseUrl(src);
  return (
    <div className={styles.deck}>
      <div className={styles.bar}>
        <span className={styles.label}>▶ {title}</span>
        <a
          className={styles.full}
          href={url}
          target="_blank"
          rel="noopener noreferrer">
          Open fullscreen ↗
        </a>
      </div>
      <div className={styles.frame}>
        <iframe
          src={url}
          title={title}
          loading="lazy"
          allowFullScreen
        />
      </div>
    </div>
  );
}
