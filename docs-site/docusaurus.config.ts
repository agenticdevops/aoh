import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'AOH — Agentic Ops Harness',
  tagline: 'Superpowers for Ops: portable, evaluated, git-versioned skills for agentic DevOps, SRE, Platform, and MLOps',
  favicon: 'img/favicon.ico',
  url: 'https://agenticdevops.github.io',
  baseUrl: '/aoh/',
  organizationName: 'agenticdevops',
  projectName: 'aoh',
  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',
  markdown: {mermaid: true},
  themes: ['@docusaurus/theme-mermaid'],
  i18n: {defaultLocale: 'en', locales: ['en']},
  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/agenticdevops/aoh/tree/main/docs-site/',
        },
        blog: {
          routeBasePath: 'field-notes',
          blogTitle: 'AOH Field Notes',
          blogDescription: 'Build-in-public notes on building the Agentic Ops Harness',
          blogSidebarTitle: 'Recent field notes',
          blogSidebarCount: 'ALL',
          showReadingTime: true,
          feedOptions: {type: ['rss', 'atom'], title: 'AOH Field Notes'},
        },
        theme: {customCss: './src/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],
  themeConfig: {
    navbar: {
      title: 'AOH',
      items: [
        {type: 'docSidebar', sidebarId: 'docs', position: 'left', label: 'Docs'},
        {to: '/field-notes', label: 'Field Notes', position: 'left'},
        {href: 'https://github.com/agenticdevops/aoh', label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {title: 'Docs', items: [
          {label: 'What is AOH', to: '/docs/concepts/what-is-aoh'},
          {label: 'Getting Started', to: '/docs/getting-started/install'},
          {label: 'Tutorials', to: '/docs/tutorials/build-a-pack'},
        ]},
        {title: 'More', items: [
          {label: 'Field Notes', to: '/field-notes'},
          {label: 'GitHub', href: 'https://github.com/agenticdevops/aoh'},
        ]},
      ],
      copyright: `Gourav Shah — Initcron AI / OpsFlow LLC / School of DevOps. Built ${new Date().getFullYear()}.`,
    },
    prism: {theme: prismThemes.github, darkTheme: prismThemes.dracula},
  } satisfies Preset.ThemeConfig,
};

export default config;
