"""Deterministic frame-index sampling, independent of time and image content."""


def uniform_frame_indices(frame_count: int, sample_count: int) -> list[int]:
    """Return min(F, N) unique points including both ends (one point for F=1).

    Integer rational rounding avoids float precision loss; ties round to even,
    like Python round. The caller must confirm the F < N fallback with users.
    """
    if type(frame_count) is not int or frame_count < 1:
        raise ValueError('frame_count must be a positive integer')
    if type(sample_count) is not int or sample_count < 2:
        raise ValueError('sample_count must be an integer >= 2')
    count = min(frame_count, sample_count)
    if count == 1:
        return [0]
    result = []
    for i in range(count):
        q, r = divmod(i * (frame_count - 1), count - 1)
        index = q + int(2*r > count-1 or (2*r == count-1 and q % 2 == 1))
        # Deterministic guard: reserve one index for each remaining point.
        index = min(max(index, result[-1]+1 if result else 0), frame_count-count+i)
        result.append(index)
    if len(set(result)) != count or result[0] != 0 or result[-1] != frame_count-1:
        raise ValueError('Uniform sampling invariant failed')
    return result
