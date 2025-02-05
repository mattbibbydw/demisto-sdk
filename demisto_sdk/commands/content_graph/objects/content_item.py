from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Set

from demisto_sdk.commands.common.handlers import JSON_Handler, XSOAR_Handler, YAML_Handler

if TYPE_CHECKING:
    from demisto_sdk.commands.content_graph.objects.pack import Pack
    from demisto_sdk.commands.content_graph.objects.relationship import RelationshipData
    from demisto_sdk.commands.content_graph.objects.test_playbook import TestPlaybook

import logging

from pydantic import DirectoryPath

from demisto_sdk.commands.common.constants import MarketplaceVersions
from demisto_sdk.commands.common.tools import alternate_item_fields
from demisto_sdk.commands.content_graph.common import ContentType, RelationshipType
from demisto_sdk.commands.content_graph.objects.base_content import BaseContent

logger = logging.getLogger("demisto-sdk")


class ContentItem(BaseContent):
    path: Path
    marketplaces: List[MarketplaceVersions]
    name: str
    fromversion: str
    toversion: str
    display_name: str
    deprecated: bool
    description: Optional[str]
    is_test: bool = False

    @property
    def in_pack(self) -> Optional["Pack"]:
        """
        This returns the Pack which the content item is in.

        Returns:
            Pack: Pack model.
        """
        in_pack = self.relationships_data[RelationshipType.IN_PACK]
        if not in_pack:
            return None
        return next(iter(in_pack)).content_item  # type: ignore[return-value]

    @property
    def uses(self) -> List["RelationshipData"]:
        """
        This returns the content items which this content item uses.
        In addition, we can tell if it's a mandatorily use or not.

        Returns:
            List[RelationshipData]:
                RelationshipData:
                    relationship_type: RelationshipType
                    source: BaseContent
                    target: BaseContent

                    # this is the attribute we're interested in when querying
                    content_item: BaseContent

                    # Whether the relationship between items is direct or not
                    is_direct: bool

                    # Whether using the command mandatorily (or optional)
                    mandatorily: bool = False

        """
        return [
            r
            for r in self.relationships_data[RelationshipType.USES]
            if r.content_item == r.target
        ]

    @property
    def tested_by(self) -> List["TestPlaybook"]:
        """
        This returns the test playbooks which the content item is tested by.

        Returns:
            List[TestPlaybook]: List of TestPlaybook models.
        """
        return [
            r.content_item  # type: ignore[misc]
            for r in self.relationships_data[RelationshipType.TESTED_BY]
            if r.content_item == r.target
        ]

    @property
    def handler(self) -> XSOAR_Handler:
        return JSON_Handler() if self.path.suffix.lower() == ".json" else YAML_Handler()

    @property
    def data(self) -> dict:
        with self.path.open() as f:
            return self.handler.load(f)

    def fix_for_marketplace(self, marketplace: Optional[MarketplaceVersions] = None) -> None:
        if marketplace and marketplace != MarketplaceVersions.XSOAR:
            data = self.data
            self.object_id = data.get('commonfields', {}).get('id_x2') or self.object_id
            self.name = data.get('name_x2') or self.name

    def prepare_for_upload(self, marketplace: MarketplaceVersions = MarketplaceVersions.XSOAR, **kwargs) -> dict:
        data = self.data
        if marketplace != MarketplaceVersions.XSOAR:
            alternate_item_fields(data)
        return data

    def summary(self) -> dict:
        """Summary of a content item (the most important metadata fields)

        Args:

        Returns:
            dict: Dictionary representation of the summary content item.
        """
        return self.dict(include=self.metadata_fields(), by_alias=True)

    @abstractmethod
    def metadata_fields(self) -> Set[str]:
        raise NotImplementedError("Should be implemented in subclasses")

    @property
    def normalize_name(self) -> str:
        """
        This will add the server prefix of the content item to its name
        In addition it will remove the existing server_names of the name.

        Args:
            name (str): content item name.
        Returns:
            str: The normalized name.
        """
        name = self.path.name
        for prefix in ContentType.server_names():
            name = name.replace(f"{prefix}-", "")
        normalized = f"{self.content_type.server_name}-{name}"
        logger.info(f"Normalized file name from {name} to {normalized}")
        return normalized

    def dump(self, dir: DirectoryPath, _: MarketplaceVersions) -> None:
        dir.mkdir(exist_ok=True, parents=True)
        data = self.prepare_for_upload()
        with (dir / self.normalize_name).open("w") as f:
            self.handler.dump(data, f)

    def to_id_set_entity(self) -> dict:
        """
        Transform the model to content item id_set.
        This is temporarily until the content graph is fully merged.

        Returns:
            dict: id_set entiity
        """
        id_set_entity = self.dict()
        id_set_entity["file_path"] = str(self.path)
        id_set_entity["pack"] = self.in_pack.object_id  # type: ignore[union-attr]
        return id_set_entity
