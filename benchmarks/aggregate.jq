def stats:
  sort as $values
  | ($values | length) as $count
  | ($values | add / $count) as $mean
  | {
      mean: $mean,
      median: (
        if ($count % 2) == 1
        then $values[($count / 2) | floor]
        else (($values[$count / 2 - 1] + $values[$count / 2]) / 2)
        end
      ),
      min: $values[0],
      max: $values[-1],
      cv_percent: (
        if $mean == 0
        then 0
        else (
          ((map((. - $mean) * (. - $mean)) | add / $count) | sqrt)
          / $mean * 100
        )
        end
      )
    };

group_by([.case_id, (.max_concurrency | tonumber)])
| map(
    . as $group
    | {
        case_id: $group[0].case_id,
        input_len: ($group[0].input_len | tonumber),
        output_len: ($group[0].output_len | tonumber),
        concurrency: ($group[0].max_concurrency | tonumber),
        rounds: (
          $group
          | map({
              round: (.round | tonumber),
              file: .result_file,
              completed,
              failed
            })
        ),
        metrics: (
          reduce $metric_names[] as $metric (
            {};
            .[$metric] = ([$group[] | .[$metric]] | stats)
          )
        )
      }
  ) as $cases
| {
    schema_version: 1,
    run_id: $run_id,
    suite_sha256: $suite_sha256,
    cv_limit_percent: $cv_limit,
    passed: (
      $cases
      | all(
          .metrics.output_throughput.cv_percent <= $cv_limit
          and (.rounds | all(.failed == 0))
        )
    ),
    cases: $cases
  }
