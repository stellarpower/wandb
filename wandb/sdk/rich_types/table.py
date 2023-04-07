import json
import os
import pathlib
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Union

from wandb import util

from .media import Media, MediaSequence

if TYPE_CHECKING:
    import pandas as pd  # type: ignore

    from wandb.sdk.wandb_artifacts import Artifact


class Table(Media):
    RELATIVE_PATH = pathlib.Path("media") / "table"
    DEFAULT_FORMAT = "TABLE.JSON"
    OBJ_TYPE = "table-file"
    OBJ_ARTIFACT_TYPE = "table"

    def __init__(
        self,
        data: Optional[Union[Sequence, "pd.DataFrame"]] = None,
        columns: Optional[Sequence[str]] = None,
    ) -> None:
        super().__init__()
        self._data = []
        self._columns = []

        if data is None:
            self._from_list([], columns)
        elif util.is_numpy_array(data):
            self._from_numpy(data, columns)
        elif util.is_pandas_data_frame(data):
            self._from_pandas(data)
        elif isinstance(data, list):
            self._from_list(data, columns)
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")

    def _from_numpy(self, data, columns):
        data = data.tolist()
        return self._from_list(data, columns)

    def _from_pandas(self, data):
        columns = data.columns.tolist()
        data = data.values.tolist()
        return self._from_list(data, columns)

    def _from_list(self, data, columns):
        if columns is None:
            columns = ["Input", "Output", "Expected"]

        assert isinstance(columns, list), "columns must be a list"
        assert all(
            isinstance(c, (str, int)) for c in columns
        ), "columns must be a list of strings or ints"

        self._columns = columns
        for row in data:
            self.add_data(row)

    def add_data(self, data):
        assert len(data) == len(
            self._columns
        ), "data must have the same number of columns as the columns argument"

        self._data.append(data)

    def save(self, path: Union[str, os.PathLike]) -> None:
        def serialize(obj):
            if isinstance(obj, (list, tuple)):
                return [serialize(item) for item in obj]
            if isinstance(obj, dict):
                return {key: serialize(value) for key, value in obj.items()}
            if isinstance(obj, (Media, MediaSequence)):
                return obj.__class__.__name__
            return obj

        with open(path, "w") as f:
            json.dump({"columns": self._columns, "data": serialize(self._data)}, f)

    def bind_to_artifact(
        self,
        artifact: "Artifact",
    ) -> dict:
        serialized = super().bind_to_artifact(artifact)

        def serialize(obj):
            if isinstance(obj, (list, tuple)):
                return [serialize(item) for item in obj]
            if isinstance(obj, dict):
                return {key: serialize(value) for key, value in obj.items()}
            if isinstance(obj, (Media, MediaSequence)):
                return obj.bind_to_artifact(artifact)
            return obj

        data = [[serialize(item) for item in row] for row in self._data]

        serialized.update(
            {
                "columns": self._columns,
                "ncols": len(self._columns),
                "data": data,
                "nrows": len(data),
            }
        )
        return serialized

    def bind_to_run(self, run, *namespace, name: Optional[str] = None) -> None:
        """Bind this table object to a run.

        Args:
            interface: The interface to bind to.
            start: The path to the run directory.
            prefix: A path prefix to prepend to the media path.
            name: The name of the media file.
        """
        # TODO: why do we save to temp file and move seems wasteful
        self._format = self.DEFAULT_FORMAT.lower()
        with self.path.save(suffix=f".{self._format}") as p:
            self.save(p)

        super().bind_to_run(
            run,
            *namespace,
            name=name,
            suffix=f".{self._format}",
        )

    def to_json(self) -> dict:
        serialized = super().to_json()
        serialized["ncols"] = len(self._columns)
        serialized["nrows"] = len(self._data)
        return serialized


class JoinedTable(Media):
    OBJ_TYPE = "joined-table"
    OBJ_ARTIFACT_TYPE = "joined-table"

    def __init__(self, *tables: Table, join_keys: Union[str, List[str]]) -> None:
        super().__init__()
        self._tables = tables
        self._join_keys = join_keys

    def bind_to_run(self, *_) -> None:
        pass

    def to_json(self) -> Dict[str, Any]:
        if self._artifact is None:
            raise ValueError("Cannot serialize unbound media object.")
        return {
            "_type": self.OBJ_TYPE,
            "artifact_path": self._artifact.artifact_path,
        }

    def bind_to_artifact(self, artifact: "Artifact") -> dict:
        serialized = {"_type": self.OBJ_ARTIFACT_TYPE, "join_keys": self._join_keys}
        tables = [
            self._extract_table(t, artifact, i) for i, t in enumerate(self._tables)
        ]
        serialized["table1"] = tables[0]
        serialized["table2"] = tables[1]
        return serialized

    def _extract_table(self, table: Table, artifact: "Artifact", index: int) -> str:
        return ""


class PartitionedTable(Media):
    ...
