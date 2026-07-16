import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    'intro',
    {
      type: 'category',
      label: 'Concepts',
      items: [
        'concepts/what-is-aoh',
        'concepts/core-model',
        'concepts/engine-neutral',
        'concepts/safe-agents',
        'concepts/for-devops-engineers',
      ],
    },
    {
      type: 'category',
      label: 'Getting Started',
      items: ['getting-started/install', 'getting-started/first-pack', 'getting-started/first-agent'],
    },
    {
      type: 'category',
      label: 'Tutorials',
      items: [
        'tutorials/build-a-pack',
        'tutorials/kubeops-readonly',
        'tutorials/kubeops-claude-code',
        'tutorials/bindings-inventory',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      items: ['reference/pack-spec', 'reference/cli', 'reference/artifact-kinds', 'reference/adapters'],
    },
  ],
};

export default sidebars;
