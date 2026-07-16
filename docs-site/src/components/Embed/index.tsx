import React from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './styles.module.css';

export interface EmbedProps {
  /** Path relative to site root, e.g. "sims/reconcile.html" */
  src: string;
  title?: string;
  /** aspect ratio, default 16/9 */
  ratio?: string;
}

export default function Embed({ src, title = 'Interactive', ratio = '16 / 9' }: EmbedProps): JSX.Element {
  const url = useBaseUrl(src);
  return (
    <div className={styles.frame} style={{ aspectRatio: ratio }}>
      <iframe src={url} title={title} loading="lazy" allowFullScreen />
    </div>
  );
}
