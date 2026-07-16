import React, {useState} from 'react';
import styles from './styles.module.css';

export type QuizOption = {text: string; correct: boolean; explanation?: string};
export type QuizQuestion = {prompt: string; options: QuizOption[]; multiSelect?: boolean};

type State = {selected: Set<number>; checked: boolean};

function isQuestionCorrect(q: QuizQuestion, selected: Set<number>): boolean {
  const correctIdx = q.options.map((o, i) => (o.correct ? i : -1)).filter((i) => i >= 0);
  if (!q.multiSelect) return selected.size === 1 && correctIdx.includes([...selected][0]);
  return (
    selected.size === correctIdx.length &&
    [...selected].every((i) => q.options[i].correct)
  );
}

function Question({q, state, onToggle}: {q: QuizQuestion; state: State; onToggle: (i: number) => void}) {
  return (
    <div className={styles.question}>
      <p className={styles.prompt}>{q.prompt}</p>
      {q.multiSelect && <p className={styles.hint}>(select all that apply)</p>}
      <ul className={styles.options}>
        {q.options.map((opt, i) => {
          const chosen = state.selected.has(i);
          let cls = styles.option;
          if (state.checked) {
            if (opt.correct) cls += ' ' + styles.correct;
            else if (chosen) cls += ' ' + styles.incorrect;
          } else if (chosen) cls += ' ' + styles.chosen;
          return (
            <li key={i}>
              <button type="button" className={cls} disabled={state.checked} onClick={() => onToggle(i)}>
                <span className={styles.marker}>{chosen ? '●' : '○'}</span> {opt.text}
              </button>
              {state.checked && (chosen || opt.correct) && opt.explanation && (
                <p className={styles.explanation}>{opt.explanation}</p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function Quiz({questions}: {questions: QuizQuestion[]}): JSX.Element {
  const [states, setStates] = useState<State[]>(
    questions.map(() => ({selected: new Set<number>(), checked: false})),
  );

  const toggle = (qi: number, oi: number) =>
    setStates((prev) =>
      prev.map((s, i) => {
        if (i !== qi) return s;
        const selected = new Set(s.selected);
        if (questions[qi].multiSelect) {
          selected.has(oi) ? selected.delete(oi) : selected.add(oi);
        } else {
          selected.clear();
          selected.add(oi);
        }
        return {...s, selected};
      }),
    );

  const check = () => setStates((prev) => prev.map((s) => ({...s, checked: true})));
  const reset = () =>
    setStates(questions.map(() => ({selected: new Set<number>(), checked: false})));

  const allChecked = states.every((s) => s.checked);
  const score = states.filter((s, i) => isQuestionCorrect(questions[i], s.selected)).length;

  return (
    <div className={styles.quiz}>
      {questions.map((q, i) => (
        <Question key={i} q={q} state={states[i]} onToggle={(oi) => toggle(i, oi)} />
      ))}
      <div className={styles.actions}>
        <button type="button" className={styles.check} onClick={check}>Check answers</button>
        <button type="button" className={styles.resetBtn} onClick={reset}>Reset</button>
        {allChecked && (
          <span className={styles.score}>Score: {score} / {questions.length}</span>
        )}
      </div>
    </div>
  );
}
