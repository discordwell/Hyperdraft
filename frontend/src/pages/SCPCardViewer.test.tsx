import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { deckbuilderAPI } from '../services/deckbuilderApi';
import type { CardDefinitionData } from '../types/deckbuilder';
import { SCPCardViewer } from './SCPCardViewer';

vi.mock('../services/deckbuilderApi', () => ({
  deckbuilderAPI: {
    getAllCards: vi.fn(),
  },
}));

function scpCard(overrides: Partial<CardDefinitionData>): CardDefinitionData {
  return {
    name: 'Unnamed SCP Card',
    game: 'scp',
    domain: null,
    mana_cost: null,
    types: ['SCP_PROCEDURE'],
    subtypes: [],
    power: null,
    toughness: null,
    text: '',
    colors: [],
    image_url: null,
    extras: {
      scp_red_tape: 0,
      scp_clearance: 0,
      scp_containment: 0,
      scp_curiosity: 0,
      scp_hazard: 0,
      scp_skills: {},
      scp_bonus: {},
      scp_keywords: [],
      scp_alt_win: null,
      scp_expansion: 'SCP Core',
      scp_expansion_code: 'CORE',
      scp_archetype: 'foundation',
      scp_art_prompt: 'Original containment art prompt.',
    },
    ...overrides,
  };
}

function renderViewer() {
  return render(
    <MemoryRouter>
      <SCPCardViewer />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SCPCardViewer', () => {
  it('loads the whole paginated SCP card pool', async () => {
    vi.mocked(deckbuilderAPI.getAllCards)
      .mockResolvedValueOnce({
        cards: [scpCard({ name: 'Moth in the Camera', types: ['SCP_ANOMALY'], text: 'Hazardous surveillance anomaly.' })],
        total: 2,
        has_more: true,
      })
      .mockResolvedValueOnce({
        cards: [scpCard({ name: 'Junior Researcher', types: ['SCP_PERSONNEL'], text: 'Research 1.' })],
        total: 2,
        has_more: false,
      });

    renderViewer();

    expect((await screen.findAllByText('Moth in the Camera')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('Junior Researcher')).length).toBeGreaterThan(0);
    expect(deckbuilderAPI.getAllCards).toHaveBeenNthCalledWith(1, 'scp', 500, 0);
    expect(deckbuilderAPI.getAllCards).toHaveBeenNthCalledWith(2, 'scp', 500, 1);
  });

  it('filters cards by search text', async () => {
    vi.mocked(deckbuilderAPI.getAllCards).mockResolvedValue({
      cards: [
        scpCard({ name: 'Moth in the Camera', types: ['SCP_ANOMALY'], text: 'Hazardous surveillance anomaly.' }),
        scpCard({ name: 'Junior Researcher', types: ['SCP_PERSONNEL'], text: 'Research 1.' }),
      ],
      total: 2,
      has_more: false,
    });

    renderViewer();

    expect((await screen.findAllByText('Moth in the Camera')).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'junior' } });

    await waitFor(() => {
      expect(screen.queryByText('Moth in the Camera')).not.toBeInTheDocument();
    });
    expect(screen.getAllByText('Junior Researcher').length).toBeGreaterThan(0);
  });

  it('renders the generated RULES block distinct from the flavor text', async () => {
    vi.mocked(deckbuilderAPI.getAllCards).mockResolvedValue({
      cards: [
        scpCard({
          name: 'O5 Auditor',
          types: ['SCP_PERSONNEL'],
          text: 'A bureaucrat who insists on remembering.',
          extras: {
            scp_red_tape: 3,
            scp_clearance: 0,
            scp_containment: 0,
            scp_curiosity: 0,
            scp_hazard: 0,
            scp_skills: { research: 3, contain: 1 },
            scp_bonus: {},
            scp_rules: [
              'All your personnel get +1 research while this is active.',
              'Mnestic: While active, blocks antimemetic decay on your anomalies.',
            ],
            scp_keywords: ['Mnestic'],
            scp_alt_win: null,
            scp_expansion: 'SCP Core',
            scp_expansion_code: 'CORE',
            scp_archetype: 'foundation',
            scp_art_prompt: '',
          },
        }),
      ],
      total: 1,
      has_more: false,
    });

    renderViewer();

    // The generated aura rule renders in the detail pane.
    expect(
      await screen.findByText('All your personnel get +1 research while this is active.'),
    ).toBeInTheDocument();
    // The keyword reminder (its meaning, not just the bare tag) renders too.
    expect(screen.getByText(/blocks antimemetic decay/)).toBeInTheDocument();
    // The flavor text is still shown, separately from the rules.
    expect(
      screen.getAllByText('A bureaucrat who insists on remembering.').length,
    ).toBeGreaterThan(0);
  });
});
